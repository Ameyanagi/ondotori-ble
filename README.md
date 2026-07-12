# ondotori-ble

> Unofficial alpha software. This project is independent of T&D Corporation.

`ondotori-ble` is a typed Python library for receiving selected current-value
advertisements from T&D Ondotori data loggers over Bluetooth Low Energy (BLE).
It does not pair with a logger, change settings, download recorded history, or
provide a command-line interface.

```python
from ondotori_ble import read_all

for reading in read_all(duration=75):
    print(reading.serial_number, reading.model, reading.measurements)
```

## Support boundary

The package keeps unknown T&D packets observable, but it only converts a value
when the layout and conversion have adequate evidence.

| Device or family | Status | Evidence |
| --- | --- | --- |
| TR41, TR42, TR45 | Temperature decoded | T&D public example |
| TR41A, TR42A | Temperature decoded | T&D public example |
| TR43A, TR32B | Temperature and humidity decoded | T&D public example |
| Family `C3` | Raw-only; product model unassigned | Independent observation |
| RTR501B/502B/503B/505B/507B measurement modes | Not decoded | More evidence required |
| TR-7wb, TR7A, TR7A2 and related BLE layouts | Not decoded | More evidence required |
| Legacy RTR units without `B` | Out of scope | Not a BLE transport |

This alpha does **not** claim support for every T&D Bluetooth model or mode.
See the [protocol documentation](https://ameyanagi.github.io/ondotori-ble/protocol/)
for the exact evidence boundary.

## Install

Python 3.11 or newer is required. While the project is in alpha, allow
pre-releases explicitly:

```console
uv add --prerelease allow ondotori-ble
```

## Read without knowing a serial number

`read()` returns the first T&D advertisement observed before its deadline:

```python
from ondotori_ble import read

reading = read(timeout=75)
if reading.is_decoded:
    print(reading.temperature_c, reading.humidity_percent)
else:
    print(f"Raw family {reading.family_code:02X}: {reading.raw_data.hex()}")
```

Use `read("5F440123")` when the eight-digit serial is known. The serial in this
example is synthetic.

## Read every observed logger

```python
from ondotori_ble import read_all

readings = read_all(duration=75)
```

The function waits for the complete collection window and returns the newest
packet from every serial observed in that interval, sorted by serial. BLE
discovery is probabilistic: no finite duration can guarantee that every nearby
device was received. Use `decoded_only=True` to exclude raw-only packets.

## Async and server use

Async applications have matching `read_async()`, `read_all_async()`, and
`scan_async()` functions. A long-running service can use the managed stream:

```python
from ondotori_ble import stream_readings

async for reading in stream_readings(deduplicate=False):
    await repository.store(reading.as_dict())
```

`deduplicate=False` emits every received advertisement. With the default
`True`, only payload changes are emitted per serial. Storage should still use
an application-defined idempotency policy because BLE does not guarantee
exactly-once delivery.

Advanced applications can manage lifecycle and inspect health directly:

```python
from ondotori_ble import OndotoriScanner

async with OndotoriScanner() as scanner:
    async for reading in scanner:
        print(reading.as_dict())

print(scanner.state, scanner.stats, scanner.last_error)
```

## Decode an existing packet

The pure decoder does not require Bluetooth hardware:

```python
from ondotori_ble import decode_advertisement

reading = decode_advertisement(
    bytes.fromhex("2301445f00000000d2041f06000000000000")
)
assert reading.temperature_c == 23.4
assert reading.humidity_percent == 56.7
```

Bleak separates T&D's company identifier (`0x0392`) from its payload. Set
`company_id_included=True` only when input still begins with little-endian
`92 03`.

## Development

```console
uv sync --all-groups
lefthook install
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv run --group docs mkdocs build --strict
uv build --no-sources
```

The full documentation is at
[ameyanagi.github.io/ondotori-ble](https://ameyanagi.github.io/ondotori-ble/).
Ondotori, T&D, and related product names are trademarks of their respective
owner.
