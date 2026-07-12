"""Public, immutable value objects returned by the decoder and scanner."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class DeviceModel(StrEnum):
    """Ondotori model identified from verified packet evidence.

    RTR500B ``L`` variants share their base model because the larger battery
    enclosure does not change the measurement layout. Enum membership records
    a known product name; it does not by itself mean that a decoder exists.
    """

    RTR501B = "RTR501B"
    RTR502B = "RTR502B"
    RTR503B = "RTR503B"
    RTR505B = "RTR505B"
    RTR507B = "RTR507B"
    TR32B = "TR32B"
    TR41 = "TR41"
    TR42 = "TR42"
    TR45 = "TR45"
    TR41A = "TR41A"
    TR42A = "TR42A"
    TR43A = "TR43A"
    TR71A = "TR71A"
    TR72A = "TR72A"
    TR72A_S = "TR72A-S"
    TR75A = "TR75A"
    TR71A2 = "TR71A2"
    TR72A2 = "TR72A2"
    TR72A2_S = "TR72A2-S"
    TR75A2 = "TR75A2"
    TR71WB = "TR-71wb"
    TR72WB = "TR-72wb"
    TR75WB = "TR-75wb"
    UNKNOWN = "unknown"


class AdvertisementFormat(StrEnum):
    """Known layout of the T&D manufacturer-specific payload."""

    RTR500B = "rtr500b"
    TR4 = "tr4"
    TR4A = "tr4a"
    UNKNOWN = "unknown"


class EvidenceLevel(StrEnum):
    """Provenance of the model/layout interpretation for a packet."""

    PUBLISHED = "published"
    OBSERVED = "observed"
    UNKNOWN = "unknown"


class MeasurementKind(StrEnum):
    """Physical quantity represented by a measurement channel."""

    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    VOLTAGE = "voltage"
    CURRENT = "current"
    PULSE = "pulse"


class Unit(StrEnum):
    """Unit attached to a decoded sensor value."""

    CELSIUS = "°C"
    PERCENT_RH = "%RH"
    VOLT = "V"
    MILLIAMPERE = "mA"
    COUNT = "count"


_UNIT_BY_KIND = {
    MeasurementKind.TEMPERATURE: Unit.CELSIUS,
    MeasurementKind.HUMIDITY: Unit.PERCENT_RH,
    MeasurementKind.VOLTAGE: Unit.VOLT,
    MeasurementKind.CURRENT: Unit.MILLIAMPERE,
    MeasurementKind.PULSE: Unit.COUNT,
}


@dataclass(frozen=True, slots=True)
class Measurement:
    """One decoded sensor channel.

    ``value`` is ``None`` when the device advertises an invalid/sensor-error
    marker. ``raw_value`` is retained so callers can audit the conversion.
    """

    channel: int
    kind: MeasurementKind
    value: float | None
    unit: Unit
    raw_value: int

    def __post_init__(self) -> None:
        """Validate invariants shared by decoded and user-created instances."""
        if self.channel < 1:
            message = "channel must be at least 1"
            raise ValueError(message)
        if not 0 <= self.raw_value <= 0xFFFFFFFF:
            message = "raw_value must fit in an unsigned 32-bit integer"
            raise ValueError(message)
        if self.value is not None and not math.isfinite(self.value):
            message = "value must be finite when present"
            raise ValueError(message)
        if self.unit is not _UNIT_BY_KIND[self.kind]:
            message = f"unit {self.unit.value!r} does not match {self.kind.value}"
            raise ValueError(message)

    @property
    def is_valid(self) -> bool:
        """Return whether the advertisement contained a usable value."""
        return self.value is not None

    def as_dict(self) -> dict[str, int | float | str | None]:
        """Return a JSON-serializable representation."""
        return {
            "channel": self.channel,
            "kind": self.kind.value,
            "value": self.value,
            "unit": self.unit.value,
            "raw_value": self.raw_value,
        }


@dataclass(frozen=True, slots=True)
class Reading:
    """A decoded T&D BLE advertisement.

    A T&D packet from an unknown family is still returned, with
    ``model=DeviceModel.UNKNOWN`` and no measurements. This makes protocol
    changes observable instead of silently discarding them.
    """

    identifier: str
    serial_number: str
    family_code: int
    model: DeviceModel
    measurements: tuple[Measurement, ...]
    rssi: int | None
    tx_power: int | None
    observed_at: datetime
    name: str | None
    raw_data: bytes
    advertisement_format: AdvertisementFormat
    evidence: EvidenceLevel

    def __post_init__(self) -> None:
        """Validate stable public invariants."""
        if len(self.serial_number) != 8:
            message = "serial_number must contain exactly eight hexadecimal digits"
            raise ValueError(message)
        try:
            int(self.serial_number, 16)
        except ValueError as error:
            message = "serial_number must be hexadecimal"
            raise ValueError(message) from error
        if not 0 <= self.family_code <= 0xFF:
            message = "family_code must fit in an unsigned byte"
            raise ValueError(message)
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            message = "observed_at must be timezone-aware"
            raise ValueError(message)

    @property
    def serial(self) -> int:
        """Return the serial number as an integer."""
        return int(self.serial_number, 16)

    @property
    def is_decoded(self) -> bool:
        """Return whether this packet produced typed measurements."""
        return bool(self.measurements)

    @property
    def temperatures_c(self) -> tuple[float | None, ...]:
        """Return temperature channels in channel order."""
        return self.values(MeasurementKind.TEMPERATURE)

    @property
    def temperature_c(self) -> float | None:
        """Return the first temperature channel, if present and valid."""
        return next(iter(self.temperatures_c), None)

    @property
    def humidities_percent(self) -> tuple[float | None, ...]:
        """Return relative-humidity channels in channel order."""
        return self.values(MeasurementKind.HUMIDITY)

    def values(self, kind: MeasurementKind) -> tuple[float | None, ...]:
        """Return values of one measurement kind in channel order."""
        return tuple(
            measurement.value for measurement in self.measurements if measurement.kind is kind
        )

    def first_value(self, kind: MeasurementKind) -> float | None:
        """Return the first value of one measurement kind, if available."""
        return next(iter(self.values(kind)), None)

    @property
    def humidity_percent(self) -> float | None:
        """Return the first relative-humidity channel, if present and valid."""
        return self.first_value(MeasurementKind.HUMIDITY)

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-serializable representation."""
        return {
            "identifier": self.identifier,
            "serial_number": self.serial_number,
            "family_code": self.family_code,
            "model": self.model.value,
            "measurements": [measurement.as_dict() for measurement in self.measurements],
            "rssi": self.rssi,
            "tx_power": self.tx_power,
            "observed_at": self.observed_at.isoformat(),
            "name": self.name,
            "raw_data": self.raw_data.hex(),
            "advertisement_format": self.advertisement_format.value,
            "evidence": self.evidence.value,
            "is_decoded": self.is_decoded,
        }
