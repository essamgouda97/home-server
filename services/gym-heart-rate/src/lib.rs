//! Pure Bluetooth packet parsing and display formatting, independent of hardware.
use anyhow::{bail, ensure, Result};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Measurement {
    pub bpm: u16,
    pub sensor_contact_supported: bool,
    pub sensor_contact_detected: Option<bool>,
    pub energy_expended_kilojoules: Option<u16>,
    pub rr_intervals_milliseconds: Option<Vec<f64>>,
}

pub fn parse_measurement(packet: &[u8]) -> Result<Measurement> {
    ensure!(packet.len() >= 2, "Truncated heart-rate packet");
    let flags = packet[0];
    let mut offset = 1;
    let mut word = || -> Result<u16> {
        ensure!(offset + 2 <= packet.len(), "Truncated optional measurement");
        let value = u16::from_le_bytes([packet[offset], packet[offset + 1]]);
        offset += 2;
        Ok(value)
    };
    let bpm = if flags & 1 != 0 {
        word()?
    } else {
        offset += 1;
        packet[1] as u16
    };
    let energy = if flags & 8 != 0 {
        ensure!(offset + 2 <= packet.len(), "Truncated energy measurement");
        let value = u16::from_le_bytes([packet[offset], packet[offset + 1]]);
        offset += 2;
        Some(value)
    } else {
        None
    };
    let rr = if flags & 16 != 0 {
        let bytes = &packet[offset..];
        ensure!(
            !bytes.is_empty() && bytes.len() % 2 == 0 && bytes.len() <= 510,
            "Invalid RR interval payload"
        );
        Some(
            bytes
                .chunks_exact(2)
                .map(|p| u16::from_le_bytes([p[0], p[1]]) as f64 * 1000.0 / 1024.0)
                .collect(),
        )
    } else {
        if offset != packet.len() {
            bail!("Unexpected trailing measurement bytes");
        }
        None
    };
    Ok(Measurement {
        bpm,
        sensor_contact_supported: flags & 4 != 0,
        sensor_contact_detected: if flags & 4 != 0 {
            Some(flags & 2 != 0)
        } else {
            None
        },
        energy_expended_kilojoules: energy,
        rr_intervals_milliseconds: rr,
    })
}

pub fn lcd_line(bpm: Option<u16>) -> String {
    let text = match bpm {
        Some(value) if value > 0 => format!("{value:>3} BPM"),
        _ => "--- BPM".into(),
    };
    format!("{text:<16}")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn basic_bpm_does_not_invent_optional_metrics() {
        let m = parse_measurement(&[0, 94]).unwrap();
        assert_eq!(m.bpm, 94);
        assert!(!m.sensor_contact_supported);
        assert_eq!(m.sensor_contact_detected, None);
        assert_eq!(m.energy_expended_kilojoules, None);
        assert_eq!(m.rr_intervals_milliseconds, None);
    }
    #[test]
    fn full_packet_decodes_little_endian_and_rr_units() {
        let m = parse_measurement(&[0x1f, 0x2c, 1, 42, 0, 0, 4, 0, 2]).unwrap();
        assert_eq!(m.bpm, 300);
        assert_eq!(m.sensor_contact_detected, Some(true));
        assert_eq!(m.energy_expended_kilojoules, Some(42));
        assert_eq!(m.rr_intervals_milliseconds, Some(vec![1000.0, 500.0]));
    }
    #[test]
    fn malformed_packets_are_rejected() {
        for packet in [
            &[][..],
            &[1, 12],
            &[8, 80],
            &[16, 80],
            &[16, 80, 1],
            &[0, 80, 1],
        ] {
            assert!(parse_measurement(packet).is_err(), "{packet:?}");
        }
    }
    #[test]
    fn unsupported_contact_flag_remains_unknown() {
        assert_eq!(
            parse_measurement(&[2, 90]).unwrap().sensor_contact_detected,
            None
        );
    }
    #[test]
    fn missing_or_zero_is_not_a_live_number() {
        assert_eq!(lcd_line(None), "--- BPM         ");
        assert_eq!(lcd_line(Some(0)), lcd_line(None));
    }
    #[test]
    fn every_update_overwrites_old_digits() {
        assert_eq!(lcd_line(Some(123)).len(), 16);
        assert_eq!(lcd_line(Some(94)), " 94 BPM         ");
    }
}
