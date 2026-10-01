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

## Passive access-point captures

On 1 October, read-only UniFi inspection confirmed that each board was associated with its existing locked access point. After the operator accepted UniFi's Debug notice, both AP shells connected and supplied `tcpdump`. No SSH credentials were retrieved and no AP, network or device configuration was changed.

A nonpromiscuous, board-filtered capture on one AP's `br0` ran for three minutes and showed only three ARP announcements. A subsequent capture on `any` exposed that board's transit traffic. This comparison shows why the bridge-only result cannot establish an absence of cloud traffic. The exact kernel/driver forwarding path was not identified.

Each AP's `any` capture was limited to its own board, 180 seconds and 120 packets. Both reached the packet limit and showed bidirectional TCP traffic between the board and the same internet address on remote port **8883**. The captures reported zero kernel drops, but included duplicate observations from multiple interfaces; those counts are not unique-packet rates or proof of complete visibility. These midstream exchanges do not establish which peer initiated the connection.

A further passive sample on one board was limited to eight TCP PUSH packets and a 160-byte snapshot. A complete 33-byte TCP payload began with `17 03 03 00 1c`: framing consistent with a TLS-encrypted record containing 28 bytes after its five-byte header. This does not establish the negotiated TLS version, MQTT, topics, authentication or command contents. Raw captures, addresses and screenshots remain private and are excluded from Git.

Separate three-minute, board-filtered windows for TCP segments beginning with TLS handshake record type 22 printed no matching packets. These short, boundary-dependent filters do not establish that negotiation never occurs; no ClientHello, ServerHello, DNS name or SNI was verified. Both bounded capture processes returned to their shell prompts, without forcing a reconnect or reset.

No fan commands were sent by the investigator during these captures. The existing Home Assistant morning schedules ran independently; their traces and reported states were checked separately, without claiming that a particular captured packet carried a speed command.

## Leading hypothesis

The board probably uses **MQTT over TLS**. [Espressif's ESP-MQTT documentation](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s2/api-reference/protocols/mqtt.html) identifies 8883 as its default TLS port. This remains an inference from the manufacturer's port requirement, board branding and the captured remote-8883 traffic with TLS-compatible framing. No decoded MQTT exchange has verified the broker role, device credentials, topics or payloads. Closed inbound MQTT ports do not exclude an outbound MQTT client.

Capturing encrypted traffic can identify connection destinations and timing. It does not normally reveal MQTT commands: decryption needs the relevant session secrets, as described in [Wireshark's TLS guide](https://wiki.wireshark.org/TLS). Browser session secrets would not cover a board's separate connection. TLS 1.3 also uses the outer `17 03 03` header for encrypted handshake and other content, so that signature does not identify the application protocol; see [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446). Replaying encrypted TCP/TLS records is not equivalent to copying an infrared code.

## Next useful experiment

The AP Debug route now works for private, passive captures. [UniFi's debug console](https://help.ui.com/hc/en-us/articles/204909374-Connecting-to-UniFi-with-Debug-Tools-SSH) and [traffic-capture guidance](https://help.ui.com/hc/en-us/articles/204959834-Advanced-Logging-Information) describe the available surfaces. A complete private PCAP with TCP reassembly would provide stronger protocol evidence than terminal summaries and truncated samples.

1. Capture only the two units' traffic on an appropriate LAN/AP interface. Include all their traffic initially, then inspect DNS, HTTP, UDP and outbound TLS on 8883/443.
2. Record an idle baseline and exact UTC times for one normal app speed change and its restoration. Allow at least three minutes per phase, and verify reported mode, speed and motor response before retrying.
3. Observe natural DNS and TLS negotiation to identify the service, without forcing a reconnect or reset. Determine whether commands travel directly to a board or through cloud connections. A connection established before capture can lack a visible handshake.

Initial attempts were blocked by unavailable Mac capture privileges, refused gateway SSH connections and a connector without a capture action. The later AP Debug session overcame the capture-access barrier and produced private packet summaries and a bounded hex sample; no complete PCAP was exported. An ordinary Mac capture also cannot reliably observe other devices' switched unicast traffic. No network settings were changed.

A local implementation needs a verified command format, authentication, state readback and device confirmation. Offline operation requires a further controlled test without cloud access.

## Modbus and firmware alternatives

The [NARAH unit manual](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=50) documents RS-485 Modbus on **D0/D1/COM**, with SW3 selecting Modbus or Wi-Fi. Direct use normally requires an RS-485 adapter or gateway. It does not establish a stock Wi-Fi-to-Modbus bridge or simultaneous operation. The board's J7 connection alone does not establish a compatible UART protocol or replacement-firmware route. These alternatives do not yet satisfy the no-additional-hardware goal.

No wiring, switch changes, resets, firmware flashing or broker redirection were performed.
