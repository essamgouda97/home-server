mod connection;
mod lcd;

use anyhow::{ensure, Context, Result};
use btleplug::{
    api::{Central, CentralEvent, Manager as _, Peripheral as _, ScanFilter},
    platform::{Manager, Peripheral},
};
use futures_util::StreamExt;
use gym_heart_rate::{lcd_line, parse_measurement, Measurement};
use serde::{Deserialize, Serialize};
use std::{
    collections::{HashMap, HashSet},
    fs::{self, OpenOptions},
    io::Write,
    os::unix::fs::OpenOptionsExt,
    path::PathBuf,
    sync::{Arc, Condvar, Mutex},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tokio::time::{sleep, timeout};
use uuid::Uuid;

const HR: Uuid = Uuid::from_u128(0x0000180d00001000800000805f9b34fb);
const MEASUREMENT: Uuid = Uuid::from_u128(0x00002a3700001000800000805f9b34fb);

#[derive(Clone, Deserialize)]
#[serde(default, deny_unknown_fields)]
struct Config {
    device_name: String,
    device_address: Option<String>,
    display: String,
    lcd_pins_bcm: [u8; 6],
    stale_after_ms: u64,
    state_path: PathBuf,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            device_name: "Google Fitbit Air".into(),
            device_address: None,
            display: "off".into(),
            lcd_pins_bcm: [17, 27, 22, 23, 24, 25],
            stale_after_ms: 12000,
            state_path: "/var/lib/gym-pi/fitbit-live.json".into(),
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct Sample {
    #[serde(flatten)]
    measurement: Measurement,
    observed_at_ms: u64,
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct Snapshot {
    schema_version: u8,
    status: String,
    device_name: String,
    bpm: Option<u16>,
    observed_at_ms: Option<u64>,
    sensor_contact_supported: Option<bool>,
    sensor_contact_detected: Option<bool>,
    energy_expended_kilojoules: Option<u16>,
    rr_intervals_milliseconds: Option<Vec<f64>>,
    rssi_dbm: Option<i16>,
    rssi_observed_at_ms: Option<u64>,
    updated_at_ms: u64,
    recent_samples: Vec<Sample>,
    receiver: &'static str,
    message: Option<&'static str>,
}
struct Model {
    snapshot: Snapshot,
    last_seen: Option<Instant>,
    stopping: bool,
    reset_lcd: bool,
}
type Shared = Arc<(Mutex<Model>, Condvar)>;
fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn set_status(shared: &Shared, status: &str) {
    let mut model = shared.0.lock().unwrap();
    if model.snapshot.status != status {
        eprintln!("Bluetooth status: {status}");
    }
    model.snapshot.status = status.into();
    if status != "live" {
        model.last_seen = None;
    }
    shared.1.notify_all();
}
fn accept_sample(shared: &Shared, measurement: Measurement) {
    let mut model = shared.0.lock().unwrap();
    let observed = now_ms();
    model.last_seen = Some(Instant::now());
    let s = &mut model.snapshot;
    s.status = "live".into();
    s.bpm = Some(measurement.bpm);
    s.observed_at_ms = Some(observed);
    s.sensor_contact_supported = Some(measurement.sensor_contact_supported);
    s.sensor_contact_detected = measurement.sensor_contact_detected;
    s.energy_expended_kilojoules = measurement.energy_expended_kilojoules;
    s.rr_intervals_milliseconds = measurement.rr_intervals_milliseconds.clone();
    s.recent_samples.push(Sample {
        measurement,
        observed_at_ms: observed,
    });
    if s.recent_samples.len() > 90 {
        s.recent_samples.remove(0);
    }
    // Wake the LCD directly; no filesystem polling, smoothing, or artificial values.
    shared.1.notify_all();
}

fn persist(shared: &Shared, path: &PathBuf) -> Result<()> {
    let mut snapshot = shared.0.lock().unwrap().snapshot.clone();
    snapshot.updated_at_ms = now_ms();
    let tmp = path.with_extension(format!("{}.tmp", std::process::id()));
    let mut file = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .mode(0o600)
        .open(&tmp)?;
    file.write_all(&serde_json::to_vec(&snapshot)?)?;
    file.write_all(b"\n")?;
    fs::rename(tmp, path)?;
    Ok(())
}

async fn session(
    config: &Config,
    shared: &Shared,
    current: &Arc<tokio::sync::Mutex<Option<Peripheral>>>,
) -> Result<()> {
    let manager = Manager::new().await?;
    let adapter = manager
        .adapters()
        .await?
        .into_iter()
        .next()
        .context("No Bluetooth adapter")?;
    set_status(shared, "scanning");
    let mut events = adapter.events().await?;
    adapter
        .start_scan(ScanFilter { services: vec![HR] })
        .await?;
    let selected = async {
        let started = Instant::now();
        let mut matches = HashMap::new();
        while started.elapsed() < Duration::from_secs(15) {
            let event = timeout(Duration::from_secs(1), events.next()).await;
            let id = match event {
                Ok(Some(CentralEvent::DeviceDiscovered(id) | CentralEvent::DeviceUpdated(id))) => {
                    Some(id)
                }
                Ok(Some(
                    CentralEvent::ManufacturerDataAdvertisement { id, .. }
                    | CentralEvent::ServiceDataAdvertisement { id, .. }
                    | CentralEvent::ServicesAdvertisement { id, .. },
                )) => Some(id),
                _ => None,
            };
            if let Some(id) = id {
                let peripheral = adapter.peripheral(&id).await?;
                let Some(properties) = peripheral.properties().await? else {
                    continue;
                };
                let matches_identity = if let Some(address) = &config.device_address {
                    properties.address.to_string().eq_ignore_ascii_case(address)
                } else {
                    properties
                        .local_name
                        .as_deref()
                        .is_some_and(|name| name.trim().eq_ignore_ascii_case(&config.device_name))
                };
                if matches_identity && properties.services.contains(&HR) {
                    matches.insert(id, peripheral);
                }
            }
            ensure!(
                matches.len() <= 1,
                "Multiple matching trackers; configure a private device address"
            );
            // Ignore stale cached addresses and allow a short discovery window
            // before selecting, so simultaneous nearby matches remain ambiguous.
            if started.elapsed() >= Duration::from_secs(2) && !matches.is_empty() {
                return Ok(matches.into_values().next().unwrap());
            }
        }
        anyhow::bail!("Tracker not advertising near the Pi")
    }
    .await;
    // Stop scanning even when discovery fails; avoid continuous Wi-Fi/BLE radio contention.
    let _ = adapter.stop_scan().await;
    let peripheral: Peripheral = selected?;
    *current.lock().await = Some(peripheral.clone());
    set_status(shared, "connecting");
    let result = async {
        timeout(Duration::from_secs(20), peripheral.connect()).await??;
        timeout(Duration::from_secs(15), peripheral.discover_services()).await??;
        let characteristic = peripheral
            .characteristics()
            .into_iter()
            .find(|c| c.uuid == MEASUREMENT)
            .context("Tracker has no Heart Rate Measurement characteristic")?;
        let mut notifications = peripheral.notifications().await?;
        timeout(
            Duration::from_secs(10),
            peripheral.subscribe(&characteristic),
        )
        .await??;
        loop {
            let notification = connection::next_connected(&mut notifications, || async {
                Ok(peripheral.is_connected().await?)
            })
            .await?;
            if notification.uuid != MEASUREMENT {
                continue;
            }
            // A malformed packet never refreshes the displayed reading or its timestamp.
            if let Ok(measurement) = parse_measurement(&notification.value) {
                accept_sample(shared, measurement);
            }
        }
        #[allow(unreachable_code)]
        Ok::<(), anyhow::Error>(())
    }
    .await;
    set_status(shared, "scanning");
    let _ = timeout(Duration::from_secs(3), peripheral.disconnect()).await;
    *current.lock().await = None;
    result
}

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    let config_path = match args.as_slice() {
        [_] => "/etc/gym-pi/heart-rate.json",
        [_, flag, value] if flag == "--config" => value,
        _ => anyhow::bail!("Usage: gym-heart-rate [--config /path/to/config.json]"),
    };
    let config: Config = serde_json::from_slice(&fs::read(config_path)?)?;
    ensure!(
        matches!(config.display.as_str(), "off" | "lcd1602"),
        "Unsupported display mode"
    );
    ensure!(
        (3000..=60000).contains(&config.stale_after_ms),
        "Stale interval out of range"
    );
    ensure!(
        !config.device_name.trim().is_empty(),
        "Device name cannot be empty"
    );
    ensure!(
        config
            .lcd_pins_bcm
            .iter()
            .copied()
            .collect::<HashSet<_>>()
            .len()
            == 6
            && config.lcd_pins_bcm.iter().all(|p| (2..=27).contains(p)),
        "Invalid or duplicate LCD GPIOs"
    );
    let snapshot = Snapshot {
        schema_version: 2,
        status: "starting".into(),
        device_name: config.device_name.clone(),
        bpm: None,
        observed_at_ms: None,
        sensor_contact_supported: None,
        sensor_contact_detected: None,
        energy_expended_kilojoules: None,
        rr_intervals_milliseconds: None,
        rssi_dbm: None,
        rssi_observed_at_ms: None,
        updated_at_ms: now_ms(),
        recent_samples: Vec::new(),
        receiver: "gym-pi",
        message: None,
    };
    let shared = Arc::new((
        Mutex::new(Model {
            snapshot,
            last_seen: None,
            stopping: false,
            reset_lcd: false,
        }),
        Condvar::new(),
    ));
    let display = if config.display == "lcd1602" {
        let mut lcd =
            lcd::Lcd::new(config.lcd_pins_bcm).context("LCD GPIO initialization failed")?;
        let state = shared.clone();
        let stale = Duration::from_millis(config.stale_after_ms);
        Some(thread::spawn(move || {
            let mut previous = String::new();
            loop {
                let mut model = state.0.lock().unwrap();
                if model.stopping {
                    break;
                }
                let bpm = model
                    .last_seen
                    .filter(|seen| seen.elapsed() < stale)
                    .and(model.snapshot.bpm);
                let line = lcd_line(bpm);
                let observation = model.snapshot.observed_at_ms;
                let status = model.snapshot.status.clone();
                let reset = std::mem::take(&mut model.reset_lcd);
                drop(model);
                if reset {
                    lcd.reset();
                    previous.clear();
                    eprintln!("LCD reinitialized; Bluetooth session preserved");
                }
                if line != previous {
                    lcd.line(1, &line);
                    previous = line;
                }
                let model = state.0.lock().unwrap();
                if model.stopping {
                    break;
                }
                // Condvar notifications update promptly; the timeout also enforces stale blanking.
                drop(
                    state
                        .1
                        .wait_timeout_while(model, Duration::from_millis(100), |model| {
                            !model.stopping
                                && !model.reset_lcd
                                && model.snapshot.observed_at_ms == observation
                                && model.snapshot.status == status
                        })
                        .unwrap(),
                );
            }
        }))
    } else {
        None
    };
    persist(&shared, &config.state_path)?;
    let writer_state = shared.clone();
    let path = config.state_path.clone();
    let stale = Duration::from_millis(config.stale_after_ms);
    let writer = tokio::spawn(async move {
        loop {
            sleep(Duration::from_secs(1)).await;
            {
                let mut model = writer_state.0.lock().unwrap();
                if model.snapshot.status == "live"
                    && model.last_seen.is_none_or(|seen| seen.elapsed() >= stale)
                {
                    model.snapshot.status = "connecting".into();
                    writer_state.1.notify_all();
                }
            }
            if let Err(error) = persist(&writer_state, &path) {
                eprintln!("Snapshot write failed: {error}");
            }
        }
    });
    let current = Arc::new(tokio::sync::Mutex::new(None));
    let ble_state = shared.clone();
    let ble_config = config.clone();
    let ble_current = current.clone();
    let receiver = tokio::spawn(async move {
        loop {
            if let Err(error) = session(&ble_config, &ble_state, &ble_current).await {
                // Error detail can contain device identifiers; logs only expose the category.
                let _ = error;
                set_status(&ble_state, "scanning");
            }
            sleep(Duration::from_secs(3)).await;
        }
    });
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    let mut reset_lcd =
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::user_defined1())?;
    loop {
        tokio::select! {
            _ = tokio::signal::ctrl_c() => break,
            _ = terminate.recv() => break,
            _ = reset_lcd.recv() => {
                shared.0.lock().unwrap().reset_lcd = true;
                shared.1.notify_all();
            }
        }
    }
    receiver.abort();
    if let Some(peripheral) = current.lock().await.take() {
        let _ = timeout(Duration::from_secs(3), peripheral.disconnect()).await;
    }
    writer.abort();
    set_status(&shared, "error");
    shared.0.lock().unwrap().stopping = true;
    shared.1.notify_all();
    if let Some(thread) = display {
        let _ = thread.join();
    }
    persist(&shared, &config.state_path)?;
    Ok(())
}
