# Reliability and performance

## Advertisement scanning, not a connection

Supported current values are carried in manufacturer advertisements, so the
normal path does not open a GATT connection. This avoids pairing and connection
state when a broadcast already contains the required value. It does not cover
legacy RTR radio, optical communication, or a base-unit bridge.

## Bounded callback work

`OndotoriScanner` keeps the BLE callback path bounded:

- parsing is proportional to the small advertisement payload;
- queue insertion never waits;
- a configurable queue evicts the oldest unread update when full;
- identical payloads are deduplicated per serial by default;
- immutable, slotted readings are safe to retain; and
- malformed T&D packets are counted and ignored.

`ScannerStats` reports advertisements, T&D advertisements, successfully parsed
packets, decoded packets, raw-only packets, duplicates, malformed packets, and
dropped queue entries. Counters reset whenever a new scanner run starts.

## Lifecycle and health

`ScannerState` distinguishes `stopped`, `starting`, `running`, and `failed`.
The scanner also exposes `last_advertisement_at`, `last_tandd_at`,
`last_matching_at`, and `last_error`. Start retries use bounded attempt counts and exponential delays;
`start()` and `stop()` are idempotent.

Context-manager shutdown preserves an application exception if backend cleanup
also fails. A stop sentinel remains available to every waiting consumer so a
stopped scanner does not leave another `get()` blocked indefinitely.

`stream_readings()` adds managed lifecycle for servers. It can retry exhausted
startup failures and optionally restart after a configured silent interval.
Silence detection is disabled by default because a quiet radio is not proof of
a broken backend.

## Backpressure and persistence

The default queue holds 256 readings. `latest` always retains the newest packet
per serial, while an overflowing consumer queue drops the oldest event. Monitor
`stats.dropped` if processing every advertisement matters.

BLE provides at-most-observed delivery, not exactly-once persistence. A server
should choose one of these policies:

- keep `deduplicate=True` and store only payload changes;
- use `deduplicate=False` and store every received event; or
- upsert a current-value table by serial while separately retaining selected
  events.

Database writes should happen in the consumer, never in the BLE callback.

## Platform notes

- macOS identifies peripherals with CoreBluetooth UUIDs rather than public MAC
  addresses; use the T&D serial as the application key.
- Linux generally requires BlueZ and adapter/user permissions.
- Windows enforces adapter and Bluetooth privacy permissions.
- Discovery is probabilistic. Increase the collection window for infrequent
  advertisers or busy 2.4 GHz environments.

Synchronous helpers create and close their own asyncio loop. Async applications
must use the async functions or scanner directly.
