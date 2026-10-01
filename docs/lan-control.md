# LAN control investigation

Reviewed 1 October 2026 for NARAH 160 RT units with existing SPCM NARAH Wi-Fi boards.

**Local fan control remains unproven.** The installed integration works through the Connectair cloud without additional hardware. The boards expose a local registration page, but no verified LAN speed-control endpoint has been found.

## Verified observations

A bounded 22-port TCP scan of two boards found port **80** open; the other 21 tested ports, including **443, 502, 1883 and 8883**, refused connections. This was neither an all-port scan nor a UDP scan, and says nothing about outbound connections.

One `GET /` per board returned a small HTML page with a **Generate key** button that reloads the page. There were no visible fan controls or external scripts. Registration keys and household identifiers are omitted.

The official [Connectair web client](https://www.connectairapp.com/chunk-4QP3XTLY.js) obtains a device's IP through its cloud API, requests `/device/{deviceId}/webserver/initialise`, and uses the local page's password in cloud `/device/authenticate`. Its [`LOCAL_API_URL`](https://www.connectairapp.com/chunk-ZRW4QNQ2.js) actually points to an Azure HTTPS service. Runtime fan commands use the cloud `/activator/{deviceId}` route. That JSON is not a demonstrated board command format.

The [SPCM NARAH manual](https://statics.solerpalau.com/media/import/documentation/Ins_SPCM_NARAH.pdf) describes internet-based control, local Wi-Fi provisioning, device-registration passwords and a requirement for port **8883** (English pp.19, 25–29). Its board illustration labels Espressif but does not identify the chip, pinout or serial protocol.

## Testing common Espressif interfaces

An Espressif chip does not establish a common LAN command interface. The port and protocol depend on the firmware installed by the manufacturer:

| Interface | Documented default | Purpose and condition |
| --- | --- | --- |
| [ESPHome native API](https://esphome.io/components/api/) | TCP 6053 | Device control when ESPHome firmware includes its API component. This is not an interface automatically supplied by Espressif hardware. |
| [ESPHome OTA](https://esphome.io/components/ota/esphome/) | TCP 3232 / 8266 | Firmware updates for ESP32 / ESP8266, rather than fan commands. |
| ArduinoOTA ([ESP32 source](https://github.com/espressif/arduino-esp32/blob/master/libraries/ArduinoOTA/src/ArduinoOTA.cpp), [ESP8266 source](https://github.com/esp8266/Arduino/blob/master/libraries/ArduinoOTA/ArduinoOTA.cpp)) | UDP 3232 / 8266 | Firmware-update invitations. Testing those numbers over TCP does not test ArduinoOTA over UDP. |
| [ESP-AT socket demo](https://github.com/espressif/esp-at/blob/master/main/interface/socket/README.md) | TCP 3333 | An optional, separately compiled alternative to UART AT commands; not a universal service. |

On 1 October, a fresh bounded test connected and closed TCP sockets on **80, 443, 502, 1883, 8883, 6053, 8266, 3232 and 3333**, with at most two concurrent probes and no application payloads. Both boards accepted **80** and refused every other tested port. One initially inconclusive 3232 connection was checked with a bounded nonblocking connect; both boards then explicitly refused it. No ESPHome or AT identification handshake could be attempted because their tested default ports refused connections.

An eight-second mDNS browse for `_esphomelib._tcp` found one advertisement; private hostname/address resolution showed it belonged to neither board. An eight-second `_arduino._tcp` browse found no advertisements. Short discovery windows do not prove a service absent, and no unicast UDP OTA probes were sent. This was neither an all-port scan nor a test of every possible vendor HTTP endpoint.

Fresh read-only UniFi client information confirmed both units online with nonzero aggregate traffic. DPI supplied no application entries, and the connector provided no remote destination/port tuples or packet-capture reader. These results do not identify MQTT, its broker, or a command format.

We have enough information to test listener availability, but not to issue a verified local fan command. The tested default interfaces did not expose a usable API; an undocumented port or HTTP route remains possible. No fan commands, update invitations, provisioning commands or firmware changes were sent during this experiment. Local control still needs vendor protocol documentation or traffic evidence.

## Leading hypothesis

The board probably connects outward using **MQTT over TLS**. [Espressif's ESP-MQTT documentation](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s2/api-reference/protocols/mqtt.html) identifies 8883 as its default TLS port. This is an inference from the manufacturer's port requirement and board branding. No packet capture has verified the broker, transport, device credentials, topics or payloads. Closed inbound MQTT ports do not exclude an outbound MQTT client.

Capturing encrypted traffic can identify connection destinations and timing. It does not normally reveal MQTT commands: decryption needs the relevant session secrets, as described in [Wireshark's TLS guide](https://wiki.wireshark.org/TLS). Replaying encrypted TCP/TLS records is not equivalent to copying an infrared code.

## Next useful experiment

Use an existing UniFi access point or gateway for a private, passive capture. [UniFi's debug console](https://help.ui.com/hc/en-us/articles/204909374-Connecting-to-UniFi-with-Debug-Tools-SSH) and [traffic-capture guidance](https://help.ui.com/hc/en-us/articles/204959834-Advanced-Logging-Information) describe the available surfaces.

1. Capture only the two units' traffic on an appropriate LAN/AP interface. Include all their traffic initially, then inspect DNS, HTTP, UDP and outbound TLS on 8883/443.
2. Record an idle baseline and exact UTC times for one normal app speed change and its restoration. Allow at least three minutes per phase, and verify reported mode, speed and motor response before retrying.
3. Determine whether commands travel directly to a board or only through cloud connections. A connection established before capture can lack a visible handshake.

No PCAP was obtained with current access: Mac packet capture required unavailable privileges, gateway SSH refused connections, and the available connector exposed no capture action. No network settings were changed. An ordinary Mac capture also cannot reliably observe other devices' switched unicast traffic.

A local implementation needs a verified command format, authentication, state readback and device confirmation. Offline operation requires a further controlled test without cloud access.

## Modbus and firmware alternatives

The [NARAH unit manual](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=50) documents RS-485 Modbus on **D0/D1/COM**, with SW3 selecting Modbus or Wi-Fi. Direct use normally requires an RS-485 adapter or gateway. It does not establish a stock Wi-Fi-to-Modbus bridge or simultaneous operation. The board's J7 connection alone does not establish a compatible UART protocol or replacement-firmware route. These alternatives do not yet satisfy the no-additional-hardware goal.

No wiring, switch changes, resets, firmware flashing or broker redirection were performed.
