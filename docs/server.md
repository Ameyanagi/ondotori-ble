# Recording readings in a server

Run one scanner for the lifetime of a host process. Do not start a BLE scan for
each HTTP request, and do not let every web worker open its own scanner. A
dedicated collector process can write to the same database used by the API.

## Managed collector

```python
import asyncio
from collections.abc import Awaitable, Callable

from ondotori_ble import Reading, stream_readings


async def collect(store: Callable[[Reading], Awaitable[None]]) -> None:
    async for reading in stream_readings(
        deduplicate=False,
        silence_timeout=180,
        restart_delay=5,
    ):
        await store(reading)


async def main() -> None:
    await collect(repository.store)


if __name__ == "__main__":
    asyncio.run(main())
```

Cancellation automatically exits the generator and stops Bleak. An application
framework should start `collect()` in its lifespan hook and cancel/await the
task during shutdown.

## Persistence choices

For a current-value table, upsert by `serial_number` and replace the row only
when `observed_at` is newer. For an event table, store at least:

- receiver timestamp (`observed_at`);
- serial and family code;
- identified model and evidence;
- decoded measurements;
- raw payload;
- RSSI and receiver identifier; and
- library version.

Advertisements do not provide exactly-once delivery. `observed_at` is the
receiver's time rather than a device event ID. If duplicate events are not
useful, use a database uniqueness policy based on the serial, raw payload, and
an application-defined time bucket, or keep the library's default
`deduplicate=True`.

## Backpressure and health

Database work runs in the async consumer, never in the BLE callback. Increase
`queue_size` only after measuring write latency, and monitor `stats.dropped`
when using `OndotoriScanner` directly.

Expose these health fields through application metrics:

- scanner state;
- last advertisement time;
- last T&D advertisement time;
- last filter-matching advertisement time;
- parsed, decoded, raw-only, malformed, duplicate, and dropped counts; and
- the most recent backend error.

`silence_timeout` is deployment-specific. Leave it disabled when no logger may
be present; enable it only when at least one device is expected to advertise
within a known maximum interval.

## Deployment boundary

The process needs host Bluetooth access and OS permission. Containers commonly
need the host Bluetooth/DBus interface explicitly mounted or forwarded. Treat
the collector as a singleton per adapter and use the database or a message
broker to fan readings out to multiple API workers.
