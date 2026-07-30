# Devices and protocol

This project processes BLE manufacturer advertisements only. Legacy RTR models
without a trailing `B`, base-unit radio collection, optical communication,
USB/serial, LAN, and cloud transports are outside its boundary.

## Advertisement boundary

T&D is assigned Bluetooth company identifier `0x0392`. Raw
manufacturer-specific data encodes it little-endian as `92 03`. Bleak exposes
the identifier as the key of `AdvertisementData.manufacturer_data`, so bytes
passed to this library normally begin with the four-byte serial rather than
the company ID.

The serial is a little-endian 32-bit integer. Its third transmitted byte is
exposed as `Reading.family_code`; a product model is assigned only when that
family mapping is supported by adequate evidence.

## Published layouts

These mappings and offsets come from T&D's public M5Stick example. Offsets are
relative to the Bleak payload after removing the company identifier.

| Family byte | Model | Channels | First value offset |
| --- | --- | --- | ---: |
| `2C`, `2D` | TR41 | temperature | 6 |
| `2E`, `2F` | TR42 | temperature | 6 |
| `30`, `31` | TR45 | temperature | 6 |
| `40`, `41` | TR41A | temperature | 8 |
| `42`, `43` | TR42A | temperature | 8 |
| `44`, `45` | TR43A | temperature, humidity | 8 |
| `46`, `47` | TR32B | temperature, humidity | 8 |

Each measurement is a little-endian unsigned 16-bit value. A usable value is:

```text
value = (raw - 1000) / 10
```

Values above `20000` are treated as sensor-error markers and produce `None`.

TR42A family `42` was also verified against a live hardware advertisement. The
public regression fixture preserves the observed packet structure with its
device identifier and serial replaced.

## Independently observed RTR505B layout

Family `C3` was verified against the printed model and serial of an RTR505B.
The connected input was also physically identified as a K thermocouple.
Repeated advertisements matched the LCD temperature:

| Field | Interpretation |
| --- | --- |
| Family byte `C3` | RTR505B |
| Byte 6 `31` | Observed temperature-mode marker |
| Bytes 8-9 | One little-endian temperature value |

The temperature uses the same offset-by-1000 tenths conversion as the published
TR layouts. The parser reports `AdvertisementFormat.RTR500B` and
`EvidenceLevel.OBSERVED` for this independently verified layout.
A fresh hardware comparison produced raw value `1282`, decoded as `28.2 °C`,
while the logger LCD simultaneously displayed `28.2 °C`.

The observed `31` marker is shared by K-thermocouple and reported Pt
temperature units; it does not distinguish their sensor technologies. Family
`C3` identifies the RTR505B regardless of input mode, but a physical
measurement is decoded only for this temperature marker. RTR505B can also use
voltage, 4–20 mA, or pulse input modules with different physical conversions.
Unverified markers therefore retain the RTR505B product name and complete
`raw_data` while leaving `measurements` empty.

The public regression fixture is synthetic: the device identifier, serial, and
nonessential packet fields do not retain the hardware values.

### Shared input modules

T&D documents `TCM-3010`, `PTM-3010`, `AIM-3010`, `VIM-3010`, and `PIC-3150`
as compatible with RTR505B, TR-55i, and legacy RTR-505 loggers. This supports
using the same physical measurement units for labelled RTR505B captures.

It does not establish a shared BLE packet layout. TR-55i communicates with a
computer through a separate TR-50U2 communication port and is therefore not a
BLE model supported by this library.

## Bluetooth capability is not advertisement evidence

Product manuals list Bluetooth communication for RTR500B, TR7A/TR7A2, and
TR-7wb families, but the public documents reviewed here do not specify a
connectionless current-value manufacturer layout for those models. Bluetooth
may instead be used for authenticated configuration or data download. This
library will not silently expand into pairing or a private GATT protocol to make
the support table appear complete.

## Unknown families

Any other packet under company ID `0x0392` remains observable with its serial,
family byte, receipt metadata, and raw payload. It carries
`EvidenceLevel.UNKNOWN` and no measurements. This lets applications retain new
firmware or models without silently converting unknown bytes.

## Decoder acceptance rule

A new decoder must provide a public protocol source or independently collected
evidence containing the exact model/module label, anonymized payloads, repeated
observations, a simultaneous display/reference value, conversion boundaries,
and error markers. Restricted specifications must not be committed or
redistributed.

## Sources

- [T&D public BLE/M5Stick example](https://www.tandd.co.jp/lab/microcontroller_browser/)
- [RTR500B remote-unit models and channels](https://tandd.com/support/webhelp/rtr500b/eng/500b-dataloggers.html)
- [RTR500B data-logger specifications](https://www.tandd.co.jp/product/spec/outline-spec-rtr500b-dataloggers-jpn.pdf)
- [RTR505B/TR-55i input-module manual](https://tandd.com/manual/pdf/man-users-rtr505b-tr55i-inputmodule-eng.pdf)
- [TR-55i product manual](https://tandd.com/manual/pdf/man-users-tr55i-eng.pdf)
- [Bluetooth SIG company identifiers](https://www.bluetooth.com/specifications/assigned-numbers/company-identifiers/)
- [T&D communication specification application](https://www.tandd.co.jp/techinfo/)

Downloaded public manuals are catalogued on the [manuals page](manuals/README.md)
but are not redistributed.
