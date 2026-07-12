# ondotori-ble

!!! warning "Unofficial alpha"
    This project is independent of T&D Corporation. It supports selected
    published advertisement layouts and does not yet cover every T&D BLE mode.

`ondotori-ble` receives current-value manufacturer advertisements from T&D
Ondotori data loggers. Its public surface consists of immutable readings, pure
packet decoders, synchronous and asynchronous one-shot reads, and a managed
async stream for servers.

```python
from ondotori_ble import read_all

for reading in read_all(duration=75):
    print(reading.serial_number, reading.measurements)
```

## Deliberately narrow scope

The library reads BLE broadcasts only. It does not change logger settings,
pair, download stored recordings, access WebStorage, or communicate over
sub-GHz radio, optical, USB, LAN, or a base-unit bridge. It contains no CLI.

## Current support

| Device or family | Result |
| --- | --- |
| TR41, TR42, TR45 | Published temperature decoder |
| TR41A, TR42A | Published temperature decoder |
| TR43A, TR32B | Published temperature/humidity decoder |
| Observed family `C3` | Raw packet with model deliberately unassigned |
| Other RTR500B, TR-7wb, TR7A, and TR7A2 BLE layouts | Retained raw until verified |
| RTR models without a trailing `B` | Outside the BLE boundary |

## Evidence and decoding are separate

Every `Reading` reports protocol provenance through `evidence`:

| Value | Meaning |
| --- | --- |
| `published` | The mapping and conversion appear in a public T&D source. |
| `observed` | A byte pattern was independently observed but is not fully identified. |
| `unknown` | No verified interpretation is assigned. |

`reading.is_decoded` independently reports whether typed measurements were
produced. An observed or recognized packet can therefore remain raw-only.

Start with the [quick start](quickstart.md), review the exact
[protocol boundary](protocol.md), and use the [reliability guide](reliability.md)
for long-running services.
