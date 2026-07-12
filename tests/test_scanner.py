from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, ClassVar, cast

import pytest
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData, AdvertisementDataCallback

import ondotori_ble.scanner as scanner_module
from ondotori_ble import (
    DeviceModel,
    OndotoriScanner,
    Reading,
    ReadingTimeoutError,
    ScannerBackend,
    ScannerState,
    ScannerUnavailableError,
    read,
    read_all,
    read_all_async,
    read_async,
    scan,
    scan_async,
    stream_readings,
)
from ondotori_ble.parser import T_AND_D_COMPANY_ID
from ondotori_ble.scanner import ScannerFactory


def make_payload(serial: str, raw: int = 1_200) -> bytes:
    payload = bytearray(18)
    payload[:4] = int(serial, 16).to_bytes(4, "little")
    payload[8:10] = raw.to_bytes(2, "little")
    return bytes(payload)


def advertisement(payload: bytes | None, *, rssi: int = -50) -> AdvertisementData:
    manufacturer_data = {} if payload is None else {T_AND_D_COMPANY_ID: payload}
    return AdvertisementData(None, manufacturer_data, {}, [], None, rssi, ())


DEVICE = BLEDevice("test-identifier", "cached-name", None)


class FakeScanner(BleakScanner):
    instances: ClassVar[list[FakeScanner]] = []
    instance_signal: ClassVar[asyncio.Event | None] = None
    failures_remaining: ClassVar[int] = 0
    emit_on_start: ClassVar[list[AdvertisementData]] = []

    def __init__(self, callback: AdvertisementDataCallback) -> None:
        self.callback = callback
        self.started = False
        self.stopped = False
        type(self).instances.append(self)
        signal = type(self).instance_signal
        if signal is not None:
            signal.set()

    async def start(self) -> None:
        if type(self).failures_remaining:
            type(self).failures_remaining -= 1
            raise OSError("transient backend error")
        self.started = True
        for data in type(self).emit_on_start:
            await self.emit(data)

    async def stop(self) -> None:
        self.stopped = True

    async def emit(self, data: AdvertisementData) -> None:
        result = self.callback(DEVICE, data)
        if isinstance(result, Coroutine):
            await result


class StopFailingScanner(FakeScanner):
    """Backend used to verify shutdown-error behavior."""

    async def stop(self) -> None:
        self.stopped = True
        raise OSError("backend stop failed")


class HangingStartScanner(FakeScanner):
    """Backend whose startup can be cancelled deterministically."""

    started_signal: ClassVar[asyncio.Event | None] = None

    async def start(self) -> None:
        if self.started_signal is not None:
            self.started_signal.set()
        await asyncio.Future()


class HangingStopScanner(FakeScanner):
    """Backend whose shutdown completes after a test-controlled release."""

    stop_started: ClassVar[asyncio.Event | None] = None
    stop_release: ClassVar[asyncio.Event | None] = None

    async def stop(self) -> None:
        if self.stop_started is not None:
            self.stop_started.set()
        if self.stop_release is not None:
            await self.stop_release.wait()
        self.stopped = True


@pytest.fixture(autouse=True)
def reset_fake_scanner() -> None:
    FakeScanner.instances = []
    FakeScanner.instance_signal = None
    FakeScanner.failures_remaining = 0
    FakeScanner.emit_on_start = []


def factory() -> ScannerFactory:
    return cast(ScannerFactory, FakeScanner)


@pytest.mark.asyncio
async def test_scanner_decodes_deduplicates_and_tracks_latest() -> None:
    scanner = OndotoriScanner(scanner_factory=factory(), retry_delay=0)
    await scanner.start()
    await scanner.start()
    backend = FakeScanner.instances[-1]

    await backend.emit(advertisement(None))
    await backend.emit(advertisement(b"bad"))
    await backend.emit(advertisement(make_payload("5F400123", 1_200), rssi=-60))
    await backend.emit(advertisement(make_payload("5F400123", 1_200), rssi=-40))
    await backend.emit(advertisement(make_payload("5F400123", 1_210), rssi=-42))

    first = await scanner.get(max_wait=0.1)
    second = await scanner.get(max_wait=0.1)
    assert first.temperature_c == 20.0
    assert second.temperature_c == 21.0
    assert scanner.latest[0].rssi == -42
    assert scanner.stats.advertisements == 5
    assert scanner.stats.tandd_advertisements == 4
    assert scanner.stats.parsed == 3
    assert scanner.stats.decoded == 3
    assert scanner.stats.raw_only == 0
    assert scanner.stats.duplicates == 1
    assert scanner.stats.malformed == 1
    assert scanner.is_running
    assert scanner.state is ScannerState.RUNNING
    assert scanner.last_advertisement_at is not None
    assert scanner.last_tandd_at is not None
    assert scanner.last_matching_at is not None

    await scanner.stop()
    await scanner.stop()
    assert not scanner.is_running
    assert scanner.state is ScannerState.STOPPED
    assert backend.stopped
    with pytest.raises(StopAsyncIteration):
        await scanner.get(max_wait=0.1)


@pytest.mark.asyncio
async def test_context_manager_and_async_iterator() -> None:
    scanner = OndotoriScanner(scanner_factory=factory())
    async with scanner:
        await FakeScanner.instances[-1].emit(advertisement(make_payload("5F400123")))
        reading = await anext(scanner.__aiter__())
        assert reading.model is DeviceModel.TR41A
    assert not scanner.is_running


@pytest.mark.asyncio
async def test_context_manager_does_not_mask_application_error() -> None:
    failing_factory = cast(ScannerFactory, StopFailingScanner)
    scanner = OndotoriScanner(scanner_factory=failing_factory)

    with pytest.raises(RuntimeError, match="application failed"):
        async with scanner:
            raise RuntimeError("application failed")

    assert scanner.state is ScannerState.FAILED
    assert isinstance(scanner.last_error, OSError)


@pytest.mark.asyncio
async def test_stop_error_is_reported_without_application_error() -> None:
    failing_factory = cast(ScannerFactory, StopFailingScanner)
    scanner = OndotoriScanner(scanner_factory=failing_factory)
    await scanner.start()

    with pytest.raises(OSError, match="backend stop failed"):
        await scanner.stop()


@pytest.mark.asyncio
async def test_cancelling_stop_waits_for_backend_cleanup() -> None:
    HangingStopScanner.stop_started = asyncio.Event()
    HangingStopScanner.stop_release = asyncio.Event()
    hanging_factory = cast(ScannerFactory, HangingStopScanner)
    scanner = OndotoriScanner(scanner_factory=hanging_factory)
    await scanner.start()
    task = asyncio.create_task(scanner.stop())
    await HangingStopScanner.stop_started.wait()

    task.cancel()
    await asyncio.sleep(0)
    HangingStopScanner.stop_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert scanner.state is ScannerState.STOPPED
    assert HangingStopScanner.instances[-1].stopped


@pytest.mark.asyncio
async def test_get_before_start_stops_immediately() -> None:
    scanner = OndotoriScanner(scanner_factory=factory())

    with pytest.raises(StopAsyncIteration):
        await scanner.get()


@pytest.mark.asyncio
async def test_stop_wakes_multiple_waiting_consumers() -> None:
    scanner = OndotoriScanner(scanner_factory=factory())
    await scanner.start()
    waiters = [asyncio.create_task(scanner.get()) for _ in range(2)]
    await asyncio.sleep(0)

    await scanner.stop()

    for waiter in waiters:
        with pytest.raises(StopAsyncIteration):
            await waiter


@pytest.mark.asyncio
async def test_stream_stops_after_idle_timeout() -> None:
    scanner = OndotoriScanner(scanner_factory=factory())
    await scanner.start()

    assert [reading async for reading in scanner.stream(idle_timeout=0.001)] == []

    await scanner.stop()


@pytest.mark.asyncio
async def test_get_validates_wait_time() -> None:
    scanner = OndotoriScanner(scanner_factory=factory())
    for bad_value in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="max_wait"):
            await scanner.get(max_wait=bad_value)


@pytest.mark.asyncio
async def test_unknown_packets_can_be_filtered() -> None:
    scanner = OndotoriScanner(include_unknown=False, scanner_factory=factory())
    await scanner.start()
    await FakeScanner.instances[-1].emit(advertisement(make_payload("12AB3456")))

    assert scanner.latest[0].model is DeviceModel.UNKNOWN
    assert scanner.stats.parsed == 1
    assert scanner.stats.decoded == 0
    assert scanner.stats.raw_only == 1
    assert scanner.last_tandd_at is not None
    assert scanner.last_matching_at is None
    with pytest.raises(TimeoutError):
        await scanner.get(max_wait=0.001)
    await scanner.stop()


@pytest.mark.asyncio
async def test_scanner_filters_serial_numbers_case_insensitively() -> None:
    scanner = OndotoriScanner(
        serial_numbers=["5f400123"],
        scanner_factory=factory(),
    )
    await scanner.start()
    backend = FakeScanner.instances[-1]
    await backend.emit(advertisement(make_payload("5F400999")))
    await backend.emit(advertisement(make_payload("5F400123")))

    reading = await scanner.get(max_wait=0.1)

    assert reading.serial_number == "5F400123"
    assert [item.serial_number for item in scanner.latest] == ["5F400123"]
    await scanner.stop()


@pytest.mark.asyncio
async def test_queue_drops_oldest_without_blocking_callback() -> None:
    scanner = OndotoriScanner(queue_size=1, deduplicate=False, scanner_factory=factory())
    await scanner.start()
    backend = FakeScanner.instances[-1]
    await backend.emit(advertisement(make_payload("5F400001", 1_200)))
    await backend.emit(advertisement(make_payload("5F400002", 1_300)))

    reading = await scanner.get(max_wait=0.1)
    assert reading.serial_number == "5F400002"
    assert scanner.stats.dropped == 1
    await scanner.stop()


@pytest.mark.asyncio
async def test_scanner_retries_start_failures() -> None:
    FakeScanner.failures_remaining = 2
    scanner = OndotoriScanner(
        scanner_factory=factory(),
        start_attempts=3,
        retry_delay=0,
    )

    await scanner.start()

    assert len(FakeScanner.instances) == 3
    assert all(instance.stopped for instance in FakeScanner.instances[:2])
    await scanner.stop()


@pytest.mark.asyncio
async def test_scanner_counters_reset_on_each_start() -> None:
    scanner = OndotoriScanner(scanner_factory=factory())
    await scanner.start()
    await FakeScanner.instances[-1].emit(advertisement(make_payload("5F400123")))
    assert scanner.stats.parsed == 1
    await scanner.stop()

    await scanner.start()

    assert scanner.stats.advertisements == 0
    assert scanner.stats.parsed == 0
    assert scanner.latest == ()
    await scanner.stop()


@pytest.mark.asyncio
async def test_scanner_wraps_exhausted_start_failures() -> None:
    FakeScanner.failures_remaining = 3
    scanner = OndotoriScanner(
        scanner_factory=factory(),
        start_attempts=3,
        retry_delay=0,
    )

    with pytest.raises(ScannerUnavailableError, match="Bluetooth permission") as captured:
        await scanner.start()

    assert isinstance(captured.value.__cause__, OSError)
    assert scanner.state is ScannerState.FAILED
    assert isinstance(scanner.last_error, OSError)


@pytest.mark.asyncio
async def test_scanner_wraps_factory_failures() -> None:
    def broken_factory(_callback: AdvertisementDataCallback) -> ScannerBackend:
        raise OSError("factory failed")

    scanner = OndotoriScanner(
        scanner_factory=broken_factory,
        start_attempts=1,
    )

    with pytest.raises(ScannerUnavailableError) as captured:
        await scanner.start()

    assert isinstance(captured.value.__cause__, OSError)
    assert scanner.state is ScannerState.FAILED


@pytest.mark.asyncio
async def test_cancelling_start_cleans_up_backend() -> None:
    HangingStartScanner.started_signal = asyncio.Event()
    hanging_factory = cast(ScannerFactory, HangingStartScanner)
    scanner = OndotoriScanner(scanner_factory=hanging_factory)
    task = asyncio.create_task(scanner.start())
    await HangingStartScanner.started_signal.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert scanner.state is ScannerState.STOPPED
    assert HangingStartScanner.instances[-1].stopped


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"queue_size": 0}, "queue_size"),
        ({"start_attempts": 0}, "start_attempts"),
        ({"retry_delay": -1}, "retry_delay"),
        ({"retry_delay": float("inf")}, "retry_delay"),
        ({"serial_numbers": []}, "serial_numbers"),
        ({"serial_numbers": "bad"}, "serial_number"),
    ],
)
def test_scanner_validates_options(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        OndotoriScanner(**kwargs)


@pytest.mark.asyncio
async def test_scan_async_returns_latest_readings() -> None:
    FakeScanner.emit_on_start = [advertisement(make_payload("5F400123"))]

    readings = await scan_async(0.001, scanner_factory=factory())

    assert len(readings) == 1
    assert readings[0].serial_number == "5F400123"


@pytest.mark.asyncio
async def test_stream_readings_manages_backend_lifecycle() -> None:
    FakeScanner.emit_on_start = [advertisement(make_payload("5F400123"))]
    readings = stream_readings(
        scanner_factory=factory(),
        restart_delay=None,
    )

    reading = await anext(readings)
    await readings.aclose()

    assert reading.serial_number == "5F400123"
    assert FakeScanner.instances[-1].stopped


@pytest.mark.asyncio
async def test_stream_readings_validates_recovery_options() -> None:
    with pytest.raises(ValueError, match="duration"):
        await anext(stream_readings(silence_timeout=0, scanner_factory=factory()))
    with pytest.raises(ValueError, match="restart_delay"):
        await anext(stream_readings(restart_delay=-1, scanner_factory=factory()))


@pytest.mark.asyncio
async def test_stream_readings_restarts_after_configured_silence() -> None:
    first_instance = asyncio.Event()
    FakeScanner.instance_signal = first_instance
    readings = stream_readings(
        silence_timeout=0.05,
        restart_delay=0.001,
        scanner_factory=factory(),
    )
    pending = asyncio.create_task(anext(readings))
    await first_instance.wait()
    second_instance = asyncio.Event()
    FakeScanner.instance_signal = second_instance

    async with asyncio.timeout(0.2):
        await second_instance.wait()

    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await readings.aclose()
    assert FakeScanner.instances[0].stopped


@pytest.mark.asyncio
async def test_stream_readings_recovers_from_exhausted_start() -> None:
    FakeScanner.failures_remaining = 1
    FakeScanner.emit_on_start = [advertisement(make_payload("5F400123"))]
    readings = stream_readings(
        start_attempts=1,
        retry_delay=0,
        restart_delay=0.001,
        scanner_factory=factory(),
    )

    reading = await anext(readings)
    await readings.aclose()

    assert reading.serial_number == "5F400123"
    assert len(FakeScanner.instances) == 2


@pytest.mark.asyncio
async def test_scan_async_forwards_serial_filter() -> None:
    FakeScanner.emit_on_start = [
        advertisement(make_payload("5F400999")),
        advertisement(make_payload("5F400123")),
    ]

    readings = await scan_async(
        0.001,
        serial_numbers="5f400123",
        scanner_factory=factory(),
    )

    assert [reading.serial_number for reading in readings] == ["5F400123"]


@pytest.mark.asyncio
async def test_scan_async_validates_duration() -> None:
    for bad_value in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="duration"):
            await scan_async(bad_value, scanner_factory=factory())


@pytest.mark.asyncio
async def test_sync_scan_refuses_running_event_loop() -> None:
    with pytest.raises(RuntimeError, match="await scan_async"):
        scan(0.001)


@pytest.mark.asyncio
async def test_read_async_returns_first_matching_reading() -> None:
    FakeScanner.emit_on_start = [
        advertisement(make_payload("5F400999")),
        advertisement(make_payload("5F400123", 1_234)),
    ]

    reading = await read_async(
        "5f400123",
        timeout=0.1,
        scanner_factory=factory(),
    )

    assert reading.serial_number == "5F400123"
    assert reading.temperature_c == 23.4


@pytest.mark.asyncio
async def test_read_async_can_return_first_tandd_device() -> None:
    FakeScanner.emit_on_start = [advertisement(make_payload("5F400123"))]

    reading = await read_async(timeout=0.1, scanner_factory=factory())

    assert reading.serial_number == "5F400123"


@pytest.mark.asyncio
async def test_read_async_decoded_only_skips_unresolved_mode() -> None:
    FakeScanner.emit_on_start = [advertisement(make_payload("00C30001"))]

    with pytest.raises(ReadingTimeoutError, match="decoded reading from serial 00C30001"):
        await read_async(
            "00C30001",
            timeout=0.001,
            decoded_only=True,
            scanner_factory=factory(),
        )


@pytest.mark.asyncio
async def test_read_async_times_out_with_context() -> None:
    with pytest.raises(ReadingTimeoutError, match=r"0\.001s.*5F400123") as captured:
        await read_async(
            "5F400123",
            timeout=0.001,
            scanner_factory=factory(),
        )

    assert isinstance(captured.value, TimeoutError)
    assert not FakeScanner.instances[-1].started or FakeScanner.instances[-1].stopped


@pytest.mark.asyncio
async def test_read_async_validates_serial_and_timeout() -> None:
    with pytest.raises(ValueError, match="serial_number"):
        await read_async("not-a-serial", scanner_factory=factory())
    with pytest.raises(ValueError, match="duration"):
        await read_async(timeout=0, scanner_factory=factory())


@pytest.mark.asyncio
async def test_read_all_async_returns_every_latest_device() -> None:
    FakeScanner.emit_on_start = [
        advertisement(make_payload("5F400123", 1_200)),
        advertisement(make_payload("00C30001", 1_300)),
    ]

    readings = await read_all_async(duration=0.001, scanner_factory=factory())

    assert [reading.serial_number for reading in readings] == ["00C30001", "5F400123"]
    assert [reading.is_decoded for reading in readings] == [False, True]


@pytest.mark.asyncio
async def test_read_all_async_can_return_decoded_only() -> None:
    FakeScanner.emit_on_start = [
        advertisement(make_payload("5F400123")),
        advertisement(make_payload("00C30001")),
    ]

    readings = await read_all_async(
        duration=0.001,
        decoded_only=True,
        scanner_factory=factory(),
    )

    assert [reading.serial_number for reading in readings] == ["5F400123"]


@pytest.mark.asyncio
async def test_read_all_async_returns_empty_tuple() -> None:
    assert await read_all_async(duration=0.001, scanner_factory=factory()) == ()


@pytest.mark.asyncio
async def test_read_all_async_validates_duration() -> None:
    with pytest.raises(ValueError, match="duration"):
        await read_all_async(duration=0, scanner_factory=factory())


@pytest.mark.asyncio
async def test_sync_read_refuses_running_event_loop() -> None:
    with pytest.raises(RuntimeError, match="await read_async"):
        read(timeout=0.001)


@pytest.mark.asyncio
async def test_sync_read_all_refuses_running_event_loop() -> None:
    with pytest.raises(RuntimeError, match="await read_all_async"):
        read_all(duration=0.001)


def test_sync_read_runs_async_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = scanner_module.decode_advertisement(make_payload("5F400123"))

    async def fake_read_async(
        serial_number: str | None,
        *,
        timeout: float,  # noqa: ASYNC109 - matches the public API signature.
        decoded_only: bool,
        start_attempts: int,
        retry_delay: float,
    ) -> Reading:
        assert serial_number == "5F400123"
        assert timeout == 2
        assert decoded_only
        assert start_attempts == 2
        assert retry_delay == 0
        return expected

    monkeypatch.setattr(scanner_module, "read_async", fake_read_async)

    assert (
        scanner_module.read(
            "5F400123",
            timeout=2,
            decoded_only=True,
            start_attempts=2,
            retry_delay=0,
        )
        is expected
    )


def test_sync_read_all_runs_async_implementation(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = (scanner_module.decode_advertisement(make_payload("5F400123")),)

    async def fake_read_all_async(
        *,
        duration: float,
        decoded_only: bool,
        start_attempts: int,
        retry_delay: float,
    ) -> tuple[Reading, ...]:
        assert duration == 2
        assert decoded_only
        assert start_attempts == 2
        assert retry_delay == 0
        return expected

    monkeypatch.setattr(scanner_module, "read_all_async", fake_read_all_async)

    assert (
        scanner_module.read_all(
            duration=2,
            decoded_only=True,
            start_attempts=2,
            retry_delay=0,
        )
        is expected
    )
