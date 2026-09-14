# Home Assistant and a house without microphones everywhere

Home Assistant Container is defined in the main Compose file. Open
`http://assistant.lan` (fallback `http://10.0.0.182:8123`), including through
Tailscale. The initial owner is `egouda`; its generated password is saved in the
Mac login Keychain under `assistant.lan`. Set the Home zone location privately
under Settings → Areas, labels & zones → Zones before enabling home/away rules.
Install the Home Assistant companion app on the phone and use
the same address. Precise coordinates, users, access tokens and device pairing
state belong in `/mnt/server/homeassistant`, not this public repository.

## What is configuration as code

- Compose owns image versions, network mode, ports, mounts and restart policy.
- `config/homeassistant/configuration.yaml` and `packages/` are read-only mounts
  from Git. Change them here and run `make home-config-check` before restart.
- `config/homeassistant/blueprints/` contains reusable automation templates.
- Home Assistant 2026.8+ manages HTTP settings through its API. Desired settings
  are in `config/homeassistant/http.json`; run `python3 scripts/configure-homeassistant.py`
  on the server to apply them. The script verifies direct and proxy access after
  restart before confirming the change, leaving automatic rollback enabled if
  checks fail. It uses a temporary login and revokes that session afterward.
  It creates the owner only on a fresh installation, preserving existing users.
  If the owner's password changes, supply the current private credential for
  reconciliation; multi-factor login requires using the settings UI instead.
- UI automations/scenes/scripts remain writable in private state. Integration
  setup, entity registries and pairing keys live in `.storage`; these are state
  to back up, not safe public configuration to commit.
- The server uses host networking for device discovery and binds its HTTP API
  to the LAN address. It does not get blanket privileged access to host devices.
  Add specific USB paths with the supplied Zigbee override once hardware exists.
- Container installations do not include Home Assistant OS's app manager.
  Additional services such as MQTT, Matter Server, or speech engines belong in
  Compose. No hardware-dependent placeholder services are started without radios.
- Core integrations are explicitly listed instead of enabling `default_config`:
  this server has no local Bluetooth adapter and does not need Bluetooth host
  management capabilities. Add Bluetooth through a supported proxy or explicit
  adapter configuration later. ESPresense room tracking uses MQTT separately.

## Existing devices

The owner's THIRDREALITY Zigbee water leak sensor is the Amazon B09GYFN8VL model.
THIRDREALITY documents pairing with both Home Assistant ZHA and Zigbee2MQTT.
No Zigbee coordinator was attached when the server USB bus was inspected.

The recommended first purchase is **Home Assistant Connect ZBT-2**, dedicated
to Zigbee and used with Home Assistant's built-in ZHA integration. Home Assistant
recommends this coordinator. It replaces the need for a separate THIRDREALITY
hub. It is not a simultaneous Zigbee-and-Thread radio. Confirm retailer stock
and Canadian pricing when purchasing; setup has not purchased anything.

After connecting it, identify its stable `/dev/serial/by-id/...` path, set
`ZIGBEE_DEVICE` privately and apply `compose.zigbee.example.yml` alongside the
main Compose file. Add ZHA using `/dev/zigbee`, put the leak sensor in pairing
mode using its manual, and select its moisture entity in the **Water leak alert**
blueprint. Select the companion app notification action after the phone is
registered. Test the sensor with a controlled small amount of water before
relying on notifications; test unavailable/battery alerts separately. The built-in
audible alarm is independent of whether HA is reachable.

### First leak sensor pairing checklist

1. Connect the Zigbee coordinator to the server and map its stable USB path with
   the Compose override. Configure **Zigbee Home Automation (ZHA)** and select
   `/dev/zigbee`; dedicate the coordinator to Zigbee.
2. Open ZHA and select **Add device**. Open the sensor's battery cover, install
   its batteries and hold its reset button for about five seconds until the LED
   is solid red. Release it; blinking blue means pairing mode. Pair close to the
   coordinator initially. See the manufacturer's [water leak FAQ](https://discuss.3reality.com/d/32-water-leak-sensor-faq).
3. Give it a location-based name, such as `Laundry leak sensor`, and assign an area.
4. Enroll the phone in the Home Assistant companion app and allow notifications.
   In Settings → Automations & scenes → Blueprints, create an automation from
   **Water leak alert**, selecting the sensor's moisture entity and the phone's
   notification action. Give that action a title/message, then save and enable it.
5. Touch a damp cloth across the bottom contacts to test it. Expect its loud
   alarm, a Wet state in HA and a phone notification. Dry the contacts and verify
   it returns to Dry. Repeat at its final location with phone Wi-Fi disabled
   and Tailscale connected. This is detection/notification, not an automatic
   water shutoff system.

For the Chromecast/Google TV device, start with **Google Cast** under Devices &
Services. It can provide media-player controls. **Android TV Remote** is another
option for supported Google TV devices and usually requires accepting a pairing
code on the television. Exact model capability should be checked before pairing;
“newest Chromecast” may mean Chromecast with Google TV or Google TV Streamer.
Setup must not interrupt playback or pair a different household device by guess.

## Voice without fixed room microphones

Start with **push-to-talk Assist on the phone**. On iPhone, the official Assist
shortcut can be assigned to an Action Button, Back Tap, or a shortcut. You carry
one microphone and invoke it intentionally. An Apple Watch can launch supported
shortcuts too. A normal two-way radio does not natively talk to Home Assistant;
a radio-style handheld voice remote would need compatible ESPHome hardware,
firmware, Wi-Fi and a battery. Treat that as a later project, not a plug-and-play
replacement for the phone.

For a fully local speech pipeline, add Wyoming Whisper (speech-to-text) and
Piper (text-to-speech) containers, then configure those integrations and an Assist
pipeline. This avoids a voice cloud subscription. The current installation's
text Assist alone does not prove that a speech pipeline is configured. Only
expose intended devices to Assist; add aliases such as “office lamp” after real
entities exist. Do not make unqualified commands such as “turn it off” depend
on an untested room estimate.

## Room awareness requested by the owner

Home/away and room tracking are separate:

1. The companion app can report home/away using the phone's location permissions.
   Set the Home zone privately and test arrivals/departures. A Tailscale connection
   by itself is not evidence that a person is at home.
2. For **which room contains a person**, mmWave occupancy sensors detect presence
   without recording audio/video, but do not establish the person's identity.
3. For **which room contains this particular person**, ESPresense can estimate
   location from a supported carried Bluetooth beacon and receivers distributed
   around the home. Start with basic room tracking in two adjacent rooms before
   buying a receiver for every room. Calibrate placement and hysteresis; Bluetooth
   signal strength crosses walls and is not an exact boundary sensor. A dedicated
   beacon is more predictable than assuming a phone always broadcasts a stable ID.

An initial shopping order is: the Zigbee coordinator, a mains-powered Zigbee
smart plug/repeater near the leak sensor if range needs it, one or two compatible
lights/plugs, then a small ESPresense/beacon trial. Verify each exact model's ZHA
or integration support and local electrical certification before buying. Add
room occupancy sensors where stationary presence matters. No camera or microphone
is required for these presence approaches. Floor plans and beacon identifiers
stay private. MQTT and presence configuration can be added to Compose after
choosing the receivers and rooms.

Room tracking, phone location, voice recognition and the leak automation are
not active yet: they require phone enrollment, the Home zone, real entity IDs
and the physical coordinator/receivers. The deployed HA UI is ready for these
steps. For the first trial, use two ESP32 receivers supported by ESPresense and
one supported dedicated beacon; add MQTT to Compose when provisioning them.

Concrete starting hardware: a [THIRDREALITY Zigbee Smart Plug Gen2](https://www.thirdreality.com/products/smart-plug-gen2-power-metering)
can control a lamp and repeat Zigbee signals; two **M5Stack Atom S3 Lite** nodes
are the ESPresense project's current [quick-start recommendation](https://espresense.com/quick-start/)
for a two-room trial. The Bluetooth beacon still needs to be chosen and enrolled.
These nodes require power and 2.4 GHz Wi-Fi; buying them alone does not enable
room tracking. Start with the coordinator and leak alert before expanding.

## Official references

- [Home Assistant Container](https://www.home-assistant.io/installation/linux)
- [Current HTTP configuration and confirmation](https://www.home-assistant.io/integrations/http)
- [ZHA and recommended coordinator](https://www.home-assistant.io/integrations/zha)
- [Connect ZBT-2](https://www.home-assistant.io/connect/zbt-2)
- [THIRDREALITY leak sensor manual](https://3reality.com/wp-content/uploads/2024/09/Water-Leak-Sensor_UM_2020925.66.pdf)
- [Google Cast](https://www.home-assistant.io/integrations/cast)
- [Android TV Remote](https://www.home-assistant.io/integrations/androidtv_remote)
- [Assist on Apple devices](https://www.home-assistant.io/voice_control/apple)
- [Fully local voice](https://www.home-assistant.io/voice_control/voice_remote_local_assistant)
- [ESPresense quick start](https://espresense.com/quick-start/)
- [ESPresense device enrollment](https://espresense.com/guides/enrolling-devices/)
