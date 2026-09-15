//! Write-only HD44780 4-bit interface. RW must be physically tied to ground.
use anyhow::Result;
use rppal::gpio::{Gpio, OutputPin};
use std::{thread, time::Duration};

pub struct Lcd {
    rs: OutputPin,
    enable: OutputPin,
    data: Vec<OutputPin>,
}
impl Lcd {
    pub fn new(pins: [u8; 6]) -> Result<Self> {
        let gpio = Gpio::new()?;
        let mut lcd = Self {
            rs: gpio.get(pins[0])?.into_output_low(),
            enable: gpio.get(pins[1])?.into_output_low(),
            data: pins[2..]
                .iter()
                .map(|p| gpio.get(*p).map(|p| p.into_output_low()))
                .collect::<Result<_, _>>()?,
        };
        lcd.reset();
        Ok(lcd)
    }
    pub fn reset(&mut self) {
        self.rs.set_low();
        self.enable.set_low();
        thread::sleep(Duration::from_millis(50));
        // Explicit initialization also recovers an LCD left in 4-bit mode after a process restart.
        for delay_ms in [5, 1, 1] {
            self.nibble(3);
            thread::sleep(Duration::from_millis(delay_ms));
        }
        self.nibble(2);
        thread::sleep(Duration::from_micros(50));
        self.byte(false, 0x28); // 4 bit, two rows, 5x8 font
        self.byte(false, 0x08); // display off during initialization
        self.byte(false, 0x01);
        thread::sleep(Duration::from_millis(2));
        self.byte(false, 0x06); // increment cursor
        self.byte(false, 0x0c); // display on, cursor and blink off
        self.line(0, "Heart rate      ");
    }
    fn nibble(&mut self, value: u8) {
        self.enable.set_low();
        for (bit, pin) in self.data.iter_mut().enumerate() {
            if value & (1 << bit) != 0 {
                pin.set_high();
            } else {
                pin.set_low();
            }
        }
        thread::sleep(Duration::from_micros(1));
        self.enable.set_high();
        thread::sleep(Duration::from_micros(1));
        self.enable.set_low();
        thread::sleep(Duration::from_micros(1));
    }
    fn byte(&mut self, data: bool, value: u8) {
        if data {
            self.rs.set_high();
        } else {
            self.rs.set_low();
        }
        self.nibble(value >> 4);
        self.nibble(value & 15);
        thread::sleep(Duration::from_micros(50));
    }
    pub fn line(&mut self, row: u8, text: &str) {
        self.byte(false, if row == 0 { 0x80 } else { 0xc0 });
        for byte in text.bytes().chain(std::iter::repeat(b' ')).take(16) {
            self.byte(true, byte);
        }
    }
}
impl Drop for Lcd {
    fn drop(&mut self) {
        self.line(1, "Stopped         ");
        self.enable.set_low();
    }
}
