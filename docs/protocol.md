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

## Independently observed family C3

Family `C3` was independently observed in the room inventory, but the exact
printed device label and attached module were not recorded at capture time.
Inventory context alone is not sufficient to make a permanent product mapping.

The parser therefore returns:

- `family_code=0xC3`;
- `model=DeviceModel.UNKNOWN`;
- `advertisement_format=AdvertisementFormat.UNKNOWN`;
- `evidence=EvidenceLevel.OBSERVED`;
- no measurements; and
- the complete Bleak payload in `raw_data`.

The public fixture is explicitly synthetic and contains no real device
identifier. Its two changing candidate words remain uninterpreted. RTR505B, for
example, can use TC, Pt, voltage, 4–20 mA, or pulse input modules with different
physical conversions, so plausible numeric output is not adequate evidence.

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
- [Bluetooth SIG company identifiers](https://www.bluetooth.com/specifications/assigned-numbers/company-identifiers/)
- [T&D communication specification application](https://www.tandd.co.jp/techinfo/)

Downloaded public manuals are catalogued on the [manuals page](manuals/README.md)
but are not redistributed.
