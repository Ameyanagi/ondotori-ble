# Quick start

## Installation

Python 3.11 or newer, a supported Bluetooth adapter, and operating-system BLE
permission are required. The current release is an alpha:

```console
uv add --prerelease allow ondotori-ble
```

## Read every observed logger

```python
from ondotori_ble import read_all

for reading in read_all(duration=75):
    print(reading.serial_number, reading.model, reading.measurements)
```

No serial numbers are required. The result contains the newest packet from
every T&D serial observed during the collection window, sorted by serial. An
empty tuple means no matching advertisement was observed; it does not prove
that no logger is nearby. Use `decoded_only=True` to omit raw-only packets.

Async code uses the matching API:

```python
from ondotori_ble import read_all_async

readings = await read_all_async(duration=75)
```

## Read one logger

```python
from ondotori_ble import read

reading = read(timeout=75)
print(reading.serial_number, reading.model)

if reading.is_decoded:
    for measurement in reading.measurements:
        print(measurement.kind, measurement.value, measurement.unit)
else:
    print(f"Raw family {reading.family_code:02X}: {reading.raw_data.hex()}")
```

`read()` without a serial returns the first observed T&D packet. Use a known
serial such as the synthetic `read("5F440123")` to wait for one logger. A
deadline raises `ReadingTimeoutError` with the target and elapsed timeout.

## Filter a snapshot

```python
from ondotori_ble import scan

readings = scan(duration=75, serial_numbers={"5F440123", "5F400123"})
for reading in readings:
    if reading.is_decoded:
        print(f"{reading.serial_number}: {reading.temperature_c} °C")
```

Omit `serial_numbers` to collect all T&D advertisements. Synchronous APIs create
their own event loop and must not be called from an existing one.

## Long-running service

The managed async generator starts and stops the backend automatically:

```python
from ondotori_ble import stream_readings

async for reading in stream_readings(deduplicate=False):
    await repository.store(reading.as_dict())
```

Set `deduplicate=False` when every received advertisement matters. The default
emits only payload changes per serial. If your deployment has a known maximum
advertising interval, `silence_timeout` can restart a quiet backend; it defaults
to `None` because radio silence can also mean no matching device is present.

For direct health and queue access:

```python
from ondotori_ble import OndotoriScanner

async with OndotoriScanner(queue_size=128) as scanner:
    async for reading in scanner.stream(idle_timeout=60):
        await repository.store(reading.as_dict())

print(scanner.state, scanner.stats, scanner.last_tandd_at, scanner.last_error)
```

## Decode without scanning

```python
from ondotori_ble import decode_manufacturer_data

reading = decode_manufacturer_data(
    {0x0392: bytes.fromhex("2301445f00000000d2041f06000000000000")},
    identifier="receiver-1",
    rssi=-61,
)
```

The result is `None` when the mapping has no T&D entry. Malformed T&D bytes
raise `MalformedAdvertisementError`. Unknown families return a raw-only
`Reading` rather than an invented measurement.
