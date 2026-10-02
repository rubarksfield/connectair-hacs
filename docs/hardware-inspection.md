# Stock Wi-Fi board inspection

Reviewed 2 October 2026. This is an assessment of the photographed board, not a verified wiring guide or working LAN integration.

## What the photographs establish

The module marking reads **ESP32-WROOM-32E**. Its lower marking ends in **N16**, consistent with the 16-MB variant in [Espressif's module datasheet](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.html). Actual flash capacity still needs a hardware read.

Visible board features include:

| Feature | Observation | Unverified function |
| --- | --- | --- |
| J2 | Six unpopulated plated holes | Programming, UART or another interface |
| J1 | Adjacent four-contact connector | Signal assignments and connected circuit |
| S1 and S3 | Two red tactile switches | Reset, boot, pairing or other action |
| S2 | Four-position DIP switch | Individual switch functions |
| D1–D4 | Four LEDs; a green LED is lit in two photos | Full indicator meanings |

There are no legible connector signal labels that establish TX, RX, ground, supply, enable or boot connections. Connector shape and the number of holes cannot establish a pinout. Raw photos include machine-readable markings and remain private; unique codes have not been decoded or published.

## Establish the connector map first

The illuminated LED means the photos do not establish electrical isolation. Isolate the fan from its supply before touching the circuitry or performing continuity measurements. Leave switches and buttons unchanged. Board supply isolation and the safe method of separately powering the Wi-Fi circuit have not been established.

With the board unpowered, trace or measure each candidate connector contact against the module's documented pads, recording orientation and measured resistance. A multimeter and a clear underside view can help distinguish direct connections, intervening components and inaccessible traces.

The following are **module pad numbers**, from Figure 3 and Table 3 of the [Espressif datasheet](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.html). They are not J1/J2 contact numbers or bare-chip pin numbers.

| Signal to locate | Module pad |
| --- | --- |
| Ground | 1, 15 or 38 |
| 3V3 supply | 2 |
| EN / chip enable | 3 |
| GPIO0 / boot strapping | 25 |
| RXD0 / GPIO3 | 34 |
| TXD0 / GPIO1 | 35 |

No contact mapping has been measured. Do not connect a serial adapter, its power output or 5-V logic to an assumed pinout. A 3.3-V-logic USB-to-UART adapter would be a temporary investigation tool; an eventual integration using the original Wi-Fi board would not inherently require that adapter to remain connected.

## Conditional firmware-read assessment

Once the electrical connections and an isolated powering method are established, start with receive-only serial observation. Boot logs may disclose build information, but their availability and contents are unknown. Keep logs private.

Espressif documents a [`read-flash` operation](https://docs.espressif.com/projects/esptool/en/latest/esp32/esptool/basic-commands.html#read-flash-contents-read-flash) for copying flash contents to a local file. This is a possible investigation route, not evidence that this board permits a readable dump. Identify the flash capacity and security configuration before choosing the read range; do not assume capacity solely from the shield marking.

Entering the ROM downloader is a separate maintenance step. It interrupts normal firmware execution and requires verified boot/enable connections; the photographed red buttons are not proven to provide them. [Espressif's boot-mode documentation](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html) describes the relevant strapping behavior.

[Esptool defaults](https://docs.espressif.com/projects/esptool/en/latest/esp32/esptool/advanced-options.html) include resetting the chip and uploading a temporary RAM stub. A prospective read must explicitly control those behaviors; `--no-stub` selects the ROM loader and has its own limitations. No esptool operation has been run against this board. No flash write, erase, security-bit change, protection bypass or replacement firmware is part of this assessment.

[Flash encryption and UART-download protections](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/security/flash-encryption.html) can prevent useful plaintext recovery. Their state on this unit is unknown. Stop at an unsupported or protected read rather than changing security settings. If readable, retain two matching copies with hashes and inspect them offline for local HTTP handlers, state/command schemas and authentication. Dumps can contain Wi-Fi and device credentials; keep them in ignored, owner-only private storage and publish only reviewed, non-sensitive findings.

The photographs identify the hardware and a candidate access area. They do not prove a programming header, a readable firmware image or operating LAN control.

## Independent investigation sequence

The recommended next sequence is connector/voltage/isolation identification, receive-only serial observation, then a conditional copy of the existing firmware for offline analysis. This uses temporary investigation equipment; it does not establish that extra hardware will be unnecessary in a completed integration. A recovered image is compiled software, not the manufacturer's original source code.

[Secure boot](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/security/secure-boot-v2.html) checks whether software is authorized to execute. Flash encryption and downloader restrictions separately affect whether a useful firmware copy can be recovered. These protections have not been read on either unit; secure boot alone must not be treated as proof that every flash read is impossible.

An alternative is passive observation of the link between the Wi-Fi module and the main fan controller while changing one setting through the working official app. A [logic analyser](https://www.saleae.com/support/getting-started/setup) can capture and decode supported digital protocols once the electrical interface has been established. The link's protocol, voltage, pinout and isolation are unknown; J1/J2/J7 must not be assumed to provide UART, I2C or Modbus. Any capture would start with passive observation rather than sending guessed commands.

That internal link may expose controller commands after network encryption has ended, but this is an untested hypothesis. Decoding it could support a replacement controller or bridge; it would not automatically add a network command handler to the stock Wi-Fi firmware. A usable stock LAN handler may be absent. The documented [RS-485 Modbus alternative](lan-control.md#modbus-and-firmware-alternatives) remains a separate route requiring permanent interface hardware and unresolved control details.

No serial connection, firmware read or internal-bus recording has been performed. These are investigation options, not verified control methods.
