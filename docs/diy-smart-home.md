# DIY smart-home direction

The owner has a Raspberry Pi 4, a Pi Zero, Arduino boards and electronics
experience, and prefers building devices. Exact Zero/Arduino/radio models and
Pi network access are still to be identified. No Pi was reimaged or deployed by
the server setup. This document is the implementation direction, not a claim
that the physical gateway is already running.

## What the coordinator does

Zigbee uses an IEEE 802.15.4 radio. A coordinator starts the Zigbee network,
admits paired devices and participates in its security. ZHA or Zigbee2MQTT
communicates with that radio and translates devices into Home Assistant entities.
There is normally one coordinator per Zigbee network. Powered router devices
extend the mesh; battery leak sensors are generally sleepy end devices.

The Pi 4's built-in Wi-Fi/Bluetooth do not provide an 802.15.4 Zigbee radio.
An ordinary Uno/Nano also needs a separate radio. A USB adapter, Pi UART/GPIO
radio module, or a supported development board with coordinator firmware is
still required. Buying the radio does not require buying a proprietary cloud hub.

## Proposed Pi 4 gateway

```mermaid
flowchart LR
  Leak[THIRDREALITY leak sensor] <-->|Zigbee| Radio[Supported coordinator radio]
  Radio <-->|USB or UART| Pi[Pi 4 running Zigbee2MQTT]
  Pi <-->|MQTT over LAN| Broker[Mosquitto on home-server]
  Broker <--> HA[Home Assistant on home-server]
  HA --> Phone[Phone alerts and Assist]
```

Use the Pi 4 on Ethernet, ideally near the center of the Zigbee coverage area.
Run Zigbee2MQTT in its own Compose deployment on the Pi; put Mosquitto beside HA
in the server Compose project. Keep radio communication local to the Pi and
send MQTT messages over the network. This avoids a fragile serial proxy over
Wi-Fi/VPN. Do not run ZHA and Zigbee2MQTT against the same coordinator.

For a first build, use a supported CC2652P/CC2652P7 or EFR32-based USB/UART
adapter with the correct coordinator firmware. For deeper hardware work,
Zigbee2MQTT documents open-source CC2652 designs and Pi GPIO modules; assemble
a proven design around a supported radio module rather than assuming any
802.15.4 chip speaks the protocol the host driver expects. Check the exact
module's supply voltage, UART levels, bootloader pins and firmware target before
wiring. ESP32-C6/H2 can be used for Zigbee firmware experiments, but their radio
capability alone does not establish compatibility as a ZHA/Zigbee2MQTT coordinator.

The earlier direct-USB ZHA plan remains valid if the main server is well located.
The Pi gateway is an alternative architecture that better uses the owner's
hardware; choose one before pairing the sensor. Preserve network keys and
coordinator backups privately to avoid unnecessary re-pairing after migration.

## Useful things to build

| Build | Parts/approach | Home Assistant connection |
|---|---|---|
| Room occupancy | ESP32 + LD2410C mmWave + USB supply/enclosure | ESPHome native API |
| Personal room location | ESP32 ESPresense receivers + a carried BLE beacon | MQTT; requires calibration |
| Handheld controls | Pi Zero or ESP32 + buttons/rotary encoder/display | MQTT or ESPHome |
| Push-to-talk voice remote | Pi + USB microphone/speaker + physical push button | Assist-compatible voice satellite |
| Custom low-voltage sensor | Arduino reads sensor, sends serial to Pi | Pi publishes MQTT |

Occupancy says someone is present; BLE tracking estimates which room contains
your particular beacon. Combine them if stationary presence and identity both
matter. ESPresense firmware targets ESP32 hardware, not the Pi directly. A Pi
can run different BLE/MQTT software, but that is a separate implementation.

The original Pi Zero has different networking/CPU capabilities from Zero W and
Zero 2 W; identify the board before selecting containers or voice software.
No microphone is needed for mmWave or BLE room sensing. Keep early DIY projects
at low voltage; use enclosed, appropriately rated products for switching mains.

## Configuration ownership

Keep a Pi Compose file, ESPHome YAML, pin maps, firmware versions, MQTT topic
conventions and deployment/check scripts in this repository when each device
is selected. Wi-Fi/MQTT passwords, Zigbee keys, beacon IDs and private floor
plans belong in runtime secrets. Hardware-specific deployments remain pending
until the radio, boards and network addresses are known.

## Primary references

- [ZHA coordinator requirements](https://www.home-assistant.io/integrations/zha)
- [Raspberry Pi 4 specifications](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/specifications/)
- [Zigbee2MQTT supported adapters](https://www.zigbee2mqtt.io/guide/adapters/)
- [CC2652 adapters, firmware and open designs](https://www.zigbee2mqtt.io/guide/adapters/zstack.html)
- [Remote adapter limitations](https://www.zigbee2mqtt.io/advanced/remote-adapter/connect_to_a_remote_adapter.html)
- [ESP32-C6 radio capabilities](https://docs.espressif.com/projects/esp-idf/en/latest/esp32c6/about.html)
- [ESPHome LD2410](https://esphome.io/components/sensor/ld2410/)
- [ESPresense nodes](https://espresense.com/nodes/)
