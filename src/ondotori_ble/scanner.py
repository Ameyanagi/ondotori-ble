"""Reliable, cross-platform BLE advertisement scanning."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import AsyncGenerator, AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData, AdvertisementDataCallback

from ondotori_ble.errors import (
    MalformedAdvertisementError,
    ReadingTimeoutError,
    ScannerUnavailableError,
)
from ondotori_ble.models import DeviceModel, Reading
from ondotori_ble.parser import T_AND_D_COMPANY_ID, decode_advertisement

_LOGGER = logging.getLogger(__name__)
_STOP = object()
_MAX_RETRY_DELAY = 30.0


class ScannerBackend(Protocol):
    """Minimal async scanner lifecycle required by :class:`OndotoriScanner`."""

    async def start(self) -> None:
        """Start delivering advertisements to the registered callback."""
        ...

    async def stop(self) -> None:
        """Stop delivering advertisements and release backend resources."""
        ...


class ScannerFactory(Protocol):
    """Create a scanner backend for a Bleak-compatible detection callback."""

    def __call__(self, callback: AdvertisementDataCallback, /) -> ScannerBackend:
        """Return a new, initially stopped backend."""
        ...


def _normalize_serial_number(serial_number: str) -> str:
    normalized = serial_number.strip().upper()
    if len(normalized) != 8:
        message = "serial_number must contain exactly eight hexadecimal digits"
        raise ValueError(message)
    try:
        int(normalized, 16)
    except ValueError as error:
        message = "serial_number must be hexadecimal"
        raise ValueError(message) from error
    return normalized


def _normalize_serial_filter(
    serial_numbers: str | Iterable[str] | None,
) -> frozenset[str] | None:
    if serial_numbers is None:
        return None
    values = (serial_numbers,) if isinstance(serial_numbers, str) else serial_numbers
    normalized = frozenset(_normalize_serial_number(value) for value in values)
    if not normalized:
        message = "serial_numbers must not be empty"
        raise ValueError(message)
    return normalized


@dataclass(frozen=True, slots=True)
class ScannerStats:
    """Point-in-time counters for the current scanner run."""

    advertisements: int
    tandd_advertisements: int
    parsed: int
    decoded: int
    raw_only: int
    duplicates: int
    malformed: int
    dropped: int


class ScannerState(StrEnum):
    """Lifecycle state of an :class:`OndotoriScanner`."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


class OndotoriScanner:
    """Continuously decode T&D advertisements without pairing or connecting.

    The callback path performs only constant-time parsing and a non-blocking
    queue write. Identical payloads are de-duplicated by default, while
    :attr:`latest` is refreshed for every observation so its timestamp and RSSI
    stay current.

    Args:
        queue_size: Maximum number of unread updates. When full, the oldest
            update is dropped so a slow consumer cannot stall the BLE backend.
        deduplicate: Emit only when a serial's manufacturer payload changes.
        include_unknown: Emit packets with T&D's company ID even when their
            serial family does not yet have a decoder.
        start_attempts: Number of attempts to start the operating-system scan.
        retry_delay: Initial delay between start attempts. It doubles after
            each failure up to 30 seconds.
        serial_numbers: Optional serial number or iterable of serial numbers to
            emit. Matching is case-insensitive.
        scanner_factory: Optional Bleak-compatible scanner factory.
    """

    def __init__(
        self,
        *,
        queue_size: int = 256,
        deduplicate: bool = True,
        include_unknown: bool = True,
        start_attempts: int = 3,
        retry_delay: float = 0.25,
        serial_numbers: str | Iterable[str] | None = None,
        scanner_factory: ScannerFactory = BleakScanner,
    ) -> None:
        if queue_size < 1:
            message = "queue_size must be at least 1"
            raise ValueError(message)
        if start_attempts < 1:
            message = "start_attempts must be at least 1"
            raise ValueError(message)
        if not math.isfinite(retry_delay) or retry_delay < 0:
            message = "retry_delay must be a finite non-negative number"
            raise ValueError(message)

        self._queue_size = queue_size
        self._queue: asyncio.Queue[Reading | object] = asyncio.Queue(maxsize=queue_size)
        self._deduplicate = deduplicate
        self._include_unknown = include_unknown
        self._start_attempts = start_attempts
        self._retry_delay = retry_delay
        self._serial_numbers = _normalize_serial_filter(serial_numbers)
        self._scanner_factory = scanner_factory
        self._scanner: ScannerBackend | None = None
        self._state = ScannerState.STOPPED
        self._state_lock = asyncio.Lock()
        self._latest: dict[str, Reading] = {}
        self._last_payload: dict[str, bytes] = {}
        self._advertisements = 0
        self._tandd_advertisements = 0
        self._parsed = 0
        self._decoded = 0
        self._raw_only = 0
        self._duplicates = 0
        self._malformed = 0
        self._dropped = 0
        self._last_advertisement_at: datetime | None = None
        self._last_tandd_at: datetime | None = None
        self._last_matching_at: datetime | None = None
        self._last_matching_monotonic: float | None = None
        self._last_error: Exception | None = None

    @property
    def is_running(self) -> bool:
        """Return whether the operating-system scan is active."""
        return self._state is ScannerState.RUNNING

    @property
    def state(self) -> ScannerState:
        """Return the scanner lifecycle state."""
        return self._state

    @property
    def last_advertisement_at(self) -> datetime | None:
        """Return when any BLE advertisement was most recently observed."""
        return self._last_advertisement_at

    @property
    def last_tandd_at(self) -> datetime | None:
        """Return when a T&D advertisement was most recently observed."""
        return self._last_tandd_at

    @property
    def last_matching_at(self) -> datetime | None:
        """Return when a packet matching this scanner's filters was last observed."""
        return self._last_matching_at

    @property
    def last_error(self) -> Exception | None:
        """Return the latest backend lifecycle error, if any."""
        return self._last_error

    @property
    def latest(self) -> tuple[Reading, ...]:
        """Return the newest reading per serial number, sorted by serial."""
        return tuple(self._latest[serial] for serial in sorted(self._latest))

    @property
    def stats(self) -> ScannerStats:
        """Return a consistent snapshot of scanner counters."""
        return ScannerStats(
            advertisements=self._advertisements,
            tandd_advertisements=self._tandd_advertisements,
            parsed=self._parsed,
            decoded=self._decoded,
            raw_only=self._raw_only,
            duplicates=self._duplicates,
            malformed=self._malformed,
            dropped=self._dropped,
        )

    def _reset_run_state(self) -> None:
        self._queue = asyncio.Queue(maxsize=self._queue_size)
        self._latest.clear()
        self._last_payload.clear()
        self._advertisements = 0
        self._tandd_advertisements = 0
        self._parsed = 0
        self._decoded = 0
        self._raw_only = 0
        self._duplicates = 0
        self._malformed = 0
        self._dropped = 0
        self._last_advertisement_at = None
        self._last_tandd_at = None
        self._last_matching_at = None
        self._last_matching_monotonic = None
        self._last_error = None

    async def start(self) -> None:
        """Start scanning, retrying transient backend failures.

        Repeated calls while running are safe and do nothing.
        """
        async with self._state_lock:
            if self._state is ScannerState.RUNNING:
                return
            self._reset_run_state()
            self._state = ScannerState.STARTING
            last_error: Exception | None = None
            for attempt in range(1, self._start_attempts + 1):
                scanner: ScannerBackend | None = None
                try:
                    scanner = self._scanner_factory(self._handle_advertisement)
                    await scanner.start()
                except asyncio.CancelledError:
                    self._state = ScannerState.STOPPED
                    if scanner is not None:
                        try:
                            await scanner.stop()
                        except Exception:
                            _LOGGER.debug(
                                "Unable to clean up cancelled scanner start", exc_info=True
                            )
                    raise
                except Exception as error:  # BLE backends expose platform exceptions.
                    last_error = error
                    self._last_error = error
                    _LOGGER.warning(
                        "Unable to start BLE scan (attempt %d/%d): %s",
                        attempt,
                        self._start_attempts,
                        error,
                    )
                    if scanner is not None:
                        try:
                            await scanner.stop()
                        except Exception:  # A partially started backend may not be stoppable.
                            _LOGGER.debug("Unable to clean up failed scanner start", exc_info=True)
                    if attempt < self._start_attempts and self._retry_delay:
                        exponent = min(attempt - 1, 16)
                        delay = min(self._retry_delay * 2**exponent, _MAX_RETRY_DELAY)
                        await asyncio.sleep(delay)
                else:
                    if scanner is None:  # pragma: no cover - protected by the successful await.
                        message = "scanner factory returned no backend"
                        raise RuntimeError(message)
                    self._scanner = scanner
                    self._state = ScannerState.RUNNING
                    return

            message = (
                "BLE scanning could not be started. Check that Bluetooth is on, "
                "this process has Bluetooth permission, and no platform service is blocked."
            )
            self._state = ScannerState.FAILED
            raise ScannerUnavailableError(message) from last_error

    async def stop(self) -> None:
        """Stop scanning and wake any stream consumers.

        Repeated calls are safe.
        """
        async with self._state_lock:
            if self._state is not ScannerState.RUNNING:
                return
            scanner = self._scanner
            self._state = ScannerState.STOPPED
            self._scanner = None
            try:
                if scanner is not None:
                    stop_task = asyncio.create_task(scanner.stop())
                    try:
                        await asyncio.shield(stop_task)
                    except asyncio.CancelledError:
                        try:
                            await stop_task
                        except Exception as error:
                            self._last_error = error
                            self._state = ScannerState.FAILED
                            _LOGGER.exception(
                                "BLE backend failed while cancellation awaited shutdown"
                            )
                        raise
            except Exception as error:
                self._last_error = error
                self._state = ScannerState.FAILED
                raise
            finally:
                self._put_nowait(_STOP, count_drop=False)

    async def __aenter__(self) -> OndotoriScanner:
        """Start scanning and return this scanner."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Stop scanning regardless of how the context exits."""
        try:
            await self.stop()
        except Exception:
            if exception is None:
                raise
            _LOGGER.exception("Unable to stop BLE scanner while handling another exception")

    def _put_nowait(self, item: Reading | object, *, count_drop: bool = True) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover - guarded by full()
                pass
            else:
                if count_drop:
                    self._dropped += 1
        self._queue.put_nowait(item)

    def _handle_advertisement(self, device: BLEDevice, data: AdvertisementData) -> None:
        self._advertisements += 1
        self._last_advertisement_at = datetime.now(UTC)
        payload = data.manufacturer_data.get(T_AND_D_COMPANY_ID)
        if payload is None:
            return
        self._tandd_advertisements += 1
        self._last_tandd_at = self._last_advertisement_at
        try:
            reading = decode_advertisement(
                payload,
                identifier=device.address,
                rssi=data.rssi,
                tx_power=data.tx_power,
                name=data.local_name or device.name,
            )
        except MalformedAdvertisementError:
            self._malformed += 1
            _LOGGER.debug("Ignoring malformed T&D advertisement", exc_info=True)
            return

        self._parsed += 1
        if reading.is_decoded:
            self._decoded += 1
        else:
            self._raw_only += 1
        if self._serial_numbers is not None and reading.serial_number not in self._serial_numbers:
            return
        self._latest[reading.serial_number] = reading
        if reading.model is DeviceModel.UNKNOWN and not self._include_unknown:
            return
        self._last_matching_at = reading.observed_at
        self._last_matching_monotonic = time.monotonic()

        previous = self._last_payload.get(reading.serial_number)
        self._last_payload[reading.serial_number] = reading.raw_data
        if self._deduplicate and previous == reading.raw_data:
            self._duplicates += 1
            return
        self._put_nowait(reading)

    async def get(self, *, max_wait: float | None = None) -> Reading:
        """Wait for one emitted reading.

        Args:
            max_wait: Maximum seconds to wait. ``None`` waits indefinitely.

        Raises:
            TimeoutError: No update arrived before ``max_wait``.
            StopAsyncIteration: The scanner stopped and its queue is empty.
        """
        if max_wait is not None and (not math.isfinite(max_wait) or max_wait <= 0):
            message = "max_wait must be a finite positive number or None"
            raise ValueError(message)
        if self._state is not ScannerState.RUNNING and self._queue.empty():
            raise StopAsyncIteration
        operation = self._queue.get()
        item = await operation if max_wait is None else await asyncio.wait_for(operation, max_wait)
        if item is _STOP:
            self._put_nowait(_STOP, count_drop=False)
            raise StopAsyncIteration
        if not isinstance(item, Reading):  # pragma: no cover - internal invariant
            message = "unexpected scanner queue item"
            raise RuntimeError(message)
        return item

    async def stream(self, *, idle_timeout: float | None = None) -> AsyncIterator[Reading]:
        """Yield updates until stopped or no update arrives before ``idle_timeout``."""
        while True:
            try:
                yield await self.get(max_wait=idle_timeout)
            except (TimeoutError, StopAsyncIteration):
                return

    def __aiter__(self) -> AsyncIterator[Reading]:
        """Iterate over :meth:`stream` with no idle timeout."""
        return self.stream()

    def _matching_silence_seconds(self) -> float | None:
        if self._last_matching_monotonic is None:
            return None
        return time.monotonic() - self._last_matching_monotonic


def _validate_duration(duration: float) -> None:
    if not math.isfinite(duration) or duration <= 0:
        message = "duration must be a finite positive number"
        raise ValueError(message)


async def scan_async(
    duration: float = 10.0,
    *,
    include_unknown: bool = True,
    start_attempts: int = 3,
    retry_delay: float = 0.25,
    serial_numbers: str | Iterable[str] | None = None,
    scanner_factory: ScannerFactory = BleakScanner,
) -> tuple[Reading, ...]:
    """Scan for a fixed duration and return the latest packet per serial.

    This is the simplest API for async applications. Use
    :class:`OndotoriScanner` when you need a continuous stream.
    """
    _validate_duration(duration)
    scanner = OndotoriScanner(
        include_unknown=include_unknown,
        start_attempts=start_attempts,
        retry_delay=retry_delay,
        serial_numbers=serial_numbers,
        scanner_factory=scanner_factory,
    )
    async with scanner:
        await asyncio.sleep(duration)
    return scanner.latest


def scan(
    duration: float = 10.0,
    *,
    include_unknown: bool = True,
    start_attempts: int = 3,
    retry_delay: float = 0.25,
    serial_numbers: str | Iterable[str] | None = None,
) -> tuple[Reading, ...]:
    """Synchronous convenience wrapper around :func:`scan_async`.

    This function intentionally refuses to nest an event loop. Async callers
    should use ``await scan_async(...)`` instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            scan_async(
                duration,
                include_unknown=include_unknown,
                start_attempts=start_attempts,
                retry_delay=retry_delay,
                serial_numbers=serial_numbers,
            )
        )
    message = "scan() cannot run inside an event loop; use 'await scan_async(...)'"
    raise RuntimeError(message)


async def read_all_async(
    *,
    duration: float = 75.0,
    decoded_only: bool = False,
    start_attempts: int = 3,
    retry_delay: float = 0.25,
    scanner_factory: ScannerFactory = BleakScanner,
) -> tuple[Reading, ...]:
    """Collect the latest reading from every T&D BLE device in range.

    Unlike :func:`read_async`, this function waits for the full collection
    window so slower advertisers also have a chance to appear. An empty tuple is
    returned when no matching devices are observed.

    Args:
        duration: Collection window in seconds. The default covers the roughly
            one-minute interval observed from an RTR500B unit.
        decoded_only: Exclude packets whose measurement mode is not decoded.
        start_attempts: Number of attempts to start the BLE backend.
        retry_delay: Initial exponential-backoff delay between start attempts.
        scanner_factory: Optional Bleak-compatible scanner factory.
    """
    readings = await scan_async(
        duration,
        include_unknown=True,
        start_attempts=start_attempts,
        retry_delay=retry_delay,
        scanner_factory=scanner_factory,
    )
    if decoded_only:
        return tuple(reading for reading in readings if reading.is_decoded)
    return readings


def read_all(
    *,
    duration: float = 75.0,
    decoded_only: bool = False,
    start_attempts: int = 3,
    retry_delay: float = 0.25,
) -> tuple[Reading, ...]:
    """Synchronous convenience wrapper around :func:`read_all_async`.

    Async callers should use ``await read_all_async(...)`` instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            read_all_async(
                duration=duration,
                decoded_only=decoded_only,
                start_attempts=start_attempts,
                retry_delay=retry_delay,
            )
        )
    message = "read_all() cannot run inside an event loop; use 'await read_all_async(...)'"
    raise RuntimeError(message)


async def stream_readings(
    *,
    queue_size: int = 256,
    deduplicate: bool = True,
    include_unknown: bool = True,
    serial_numbers: str | Iterable[str] | None = None,
    start_attempts: int = 3,
    retry_delay: float = 0.25,
    silence_timeout: float | None = None,
    restart_delay: float | None = 5.0,
    scanner_factory: ScannerFactory = BleakScanner,
) -> AsyncGenerator[Reading]:
    """Continuously yield readings while managing scanner lifecycle.

    This is the simplest API for long-running services. A configured
    ``silence_timeout`` restarts the backend when no filter-matching
    advertisement arrives in that interval, including deduplicated packets.
    Silence can also mean that no matching logger is nearby, so
    the default is ``None`` and does not infer failure from radio quietness.

    When scanner startup remains unavailable after ``start_attempts``, a
    non-``None`` ``restart_delay`` waits and retries until the consumer cancels
    iteration. Set it to ``None`` to propagate :class:`ScannerUnavailableError`.
    """
    if silence_timeout is not None:
        _validate_duration(silence_timeout)
    if restart_delay is not None and (not math.isfinite(restart_delay) or restart_delay <= 0):
        message = "restart_delay must be a finite positive number or None"
        raise ValueError(message)

    while True:
        scanner = OndotoriScanner(
            queue_size=queue_size,
            deduplicate=deduplicate,
            include_unknown=include_unknown,
            serial_numbers=serial_numbers,
            start_attempts=start_attempts,
            retry_delay=retry_delay,
            scanner_factory=scanner_factory,
        )
        try:
            async with scanner:
                while True:
                    max_wait = silence_timeout
                    elapsed = scanner._matching_silence_seconds()
                    if silence_timeout is not None and elapsed is not None:
                        max_wait = max(silence_timeout - elapsed, 0.001)
                    try:
                        yield await scanner.get(max_wait=max_wait)
                    except TimeoutError:
                        elapsed = scanner._matching_silence_seconds()
                        if (
                            silence_timeout is not None
                            and elapsed is not None
                            and elapsed < silence_timeout
                        ):
                            continue
                        _LOGGER.warning(
                            "No matching T&D reading for %.1fs; restarting BLE scan",
                            silence_timeout,
                        )
                        break
        except ScannerUnavailableError:
            if restart_delay is None:
                raise
            _LOGGER.exception(
                "BLE scanner unavailable; retrying in %.1fs",
                restart_delay,
            )
        if restart_delay:
            await asyncio.sleep(restart_delay)


async def read_async(
    serial_number: str | None = None,
    *,
    timeout: float = 75.0,  # noqa: ASYNC109 - public API names the user's deadline.
    decoded_only: bool = False,
    start_attempts: int = 3,
    retry_delay: float = 0.25,
    scanner_factory: ScannerFactory = BleakScanner,
) -> Reading:
    """Return the first matching T&D reading observed before ``timeout``.

    Args:
        serial_number: Optional eight-digit serial to wait for. When omitted,
            return the first T&D advertisement.
        timeout: Maximum scan time in seconds. The 75-second default covers the
            approximately one-minute interval observed from an RTR500B unit.
        decoded_only: Ignore recognized-but-undecoded and unknown packets.
        start_attempts: Number of attempts to start the BLE backend.
        retry_delay: Initial exponential-backoff delay between start attempts.
        scanner_factory: Optional Bleak-compatible scanner factory.

    Raises:
        ReadingTimeoutError: No matching reading arrived before ``timeout``.
        ValueError: A serial number or timeout is invalid.
    """
    _validate_duration(timeout)
    normalized = None if serial_number is None else _normalize_serial_number(serial_number)
    scanner = OndotoriScanner(
        include_unknown=True,
        start_attempts=start_attempts,
        retry_delay=retry_delay,
        serial_numbers=normalized,
        scanner_factory=scanner_factory,
    )
    try:
        async with scanner:
            async with asyncio.timeout(timeout):
                while True:
                    reading = await scanner.get()
                    if not decoded_only or reading.is_decoded:
                        return reading
    except TimeoutError as error:
        target = "a decoded reading" if decoded_only else "a T&D reading"
        if normalized is not None:
            target = f"{target} from serial {normalized}"
        message = f"Timed out after {timeout:g}s waiting for {target}"
        raise ReadingTimeoutError(message) from error


def read(
    serial_number: str | None = None,
    *,
    timeout: float = 75.0,
    decoded_only: bool = False,
    start_attempts: int = 3,
    retry_delay: float = 0.25,
) -> Reading:
    """Synchronous convenience wrapper around :func:`read_async`.

    Async callers should use ``await read_async(...)`` instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            read_async(
                serial_number,
                timeout=timeout,
                decoded_only=decoded_only,
                start_attempts=start_attempts,
                retry_delay=retry_delay,
            )
        )
    message = "read() cannot run inside an event loop; use 'await read_async(...)'"
    raise RuntimeError(message)
