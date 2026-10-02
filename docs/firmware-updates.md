# Original SPCM NARAH firmware and updates

Reviewed 2 October 2026. The update behaviour is partly documented, but the original firmware package and its delivery protocol have not been obtained. This investigation adds no LAN-control capability.

## What S&P documents

The supplied [NARAH_22375 Wi-Fi-module manual](https://mediacenter.solerpalau.com/api/materials/get/NARAH_22375.pdf?filePath=%5CMagento%5Cpreprod%5Cimport%5Cdocumentation%5CNARAH_22375.pdf&view=true) and the [SPCM NARAH manual, English p33](https://statics.solerpalau.com/media/import/documentation/Ins_SPCM_NARAH.pdf#page=33) give the same update description:

- The SPCM module checks for updates when it connects to the internet.
- It also checks overnight, at a randomized time between 00:00 and 06:00. The timezone is unspecified.
- When an update is available, the module downloads and installs it.
- All four LEDs flash rapidly during that process.

The supplied file is a Wi-Fi communication-module manual, rather than a firmware image. Its English update paragraph matches the separately published SPCM manual. This identifies the module's automatic update behaviour; it does not establish whether the ventilation control PCB is also updated, which component a cloud version field represents, or how an image is selected and authenticated.

The manuals do not identify an update host/path, manifest schema, firmware filename, signing scheme or download credential. Their description alone cannot produce a compatible downloadable image.

## What the app exposes

The [official iOS app history](https://apps.apple.com/us/app/connectair/id6446583166) records a firmware-check feature in app version 1.0.23, dated 26 October 2023. That is a mobile-app version, not a board-firmware version.

Previously inspected official web/native registration code reads cloud metadata and handles a `requiresFirmwareUpdate` flag by showing an overnight-update notice. The traced warning and registration paths supplied no image or manifest URL. Some downstream native callback effects remain unresolved; the inspected code does not establish an app-to-board firmware transfer.

Fresh public web HTML is byte-identical to the retained 1 October copy, with the same eight script references. The earlier named-script graph covers 67 retained scripts; this fresh HTML check does not freshly verify every script byte. A targeted ownership review identifies the web client's `downloadURL` occurrences as chart CSV/XLS export code, rather than a firmware downloader. Minification, encoded strings and runtime-generated paths limit lexical negatives. See the [underlying LAN investigation](lan-control.md#deeper-identity-and-firmware-investigation).

## Public repositories and supplier attribution

A focused search of manufacturer pages, app listings, legal notices, supplier sources and public repository platforms found no attributable SPCM NARAH firmware/source repository or compatible image release. This is a bounded search result, not proof that no private or unindexed package exists.

[Paramet's own ConnectAir case study](https://paramet.com/case-studies/connectair/) identifies its work rewriting the web back-end API, using C#/ASP.Net and Azure App Service. It supplies no stock firmware repository and does not establish Paramet as the Wi-Fi board's firmware developer. A first-person [app developer portfolio](https://www.johnnyhall.dev/projects) links the official Connectair listings but provides no source link for that project; app-development provenance does not establish firmware ownership.

The current S&P product links lead to Media Center. Its inspected catalogue still reports eleven results while returning ten items, so catalogue coverage remains qualified. Visible downloads supply documentation and product media. A linked website licence file describes web libraries, rather than identifying embedded firmware source. The old UK SPCM product URL now redirects to SPCM LITE, which must not be assumed compatible with this NARAH board.

There are public [Espressif Azure integration sources](https://github.com/espressif/esp-azure) and [Microsoft FreeRTOS Device Update sources](https://github.com/Azure/azure-iot-middleware-freertos/blob/4502a309bf1c300507684cd4a341c6baf6eca698/docs/how_to_use_adu_client.md). Microsoft's documented implementation delivers signed manifests and image links through device-twin update requests. These are reference implementations: the stock board's observed cloud service family does not establish that it uses this updater or its schema. No sample image is a verified replacement for S&P firmware.

## Can UniFi identify the original download?

Possibly, if the gateway retained traffic records from the update. UniFi's [Traffic Flows documentation](https://help.ui.com/hc/en-us/articles/32201256219799-Traffic-Flows-and-Traffic-Logging-in-UniFi-Network) describes completed sessions with source/destination ports, transfer sizes and durations. Its history requires supported gateway software and storage; retention depends on the number of records, rather than a guaranteed number of days. Hardware support alone does not establish that records exist for an earlier update.

The useful search is restricted to the owned fan's identity and its first connection/update window. A client `first_seen` timestamp helps choose that window but is not an update timestamp. A download-sized connection to a destination supplies a candidate server, not proof of a firmware transfer or a compatible image.

Ordinary [system logs](https://help.ui.com/hc/en-us/articles/33349041044119-UniFi-System-Logs-SIEM-Integration) record events such as Wi-Fi connections and device/admin activity. A UniFi-device update event does not establish a third-party fan's firmware update. Empty legacy event or per-client traffic-summary responses also do not establish that the newer Traffic Flows history is empty.

HTTPS normally hides the requested path, query and downloaded contents from ordinary gateway records. A retained flow may identify the destination without exposing the firmware URL. Logging enabled later cannot recover packets or records that were never retained. This investigation inspects retained records without changing logging, TLS inspection or other network settings.

The live read-only check found retained Wi-Fi connection/reconnection events for both owned fans around initial installation. Those records give connection times and session data totals, but no download destination or firmware filename. The gateway currently selects **Blocked Traffic Only**, with **All Flows** disabled in the traffic-history view; NetFlow export is off and activity logs are stored internally. That current configuration does not prove which logging mode was selected at installation. No successful update-download record, server address or firmware URL was recovered from the inspected history.

## What would unlock the next step

The useful artifact is an actual model-matched S&P/OEM image or a source-backed manifest/download reference. That could be inspected on a computer before any installation. Standard ESP32 hardware and public SDKs do not identify the appliance's installed program.

Existing encrypted traffic supplies no readable image URL or confirmed update exchange. Additional traffic alone cannot turn the encrypted payload into firmware. A readable stock-board firmware copy or startup information may provide the missing handler/download evidence; that physical route remains conditional on [connector identification and readout protections](hardware-inspection.md).

No update, reconnection, provisioning, flash or security-setting change was triggered during this research. Raw captures, board photographs, unique codes and credentials remain private. No local operating status, speed command or offline operation has been established.
