"""Pure functions for decoding T&D manufacturer-specific BLE data."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from ondotori_ble.errors import MalformedAdvertisementError, NotOndotoriAdvertisementError
from ondotori_ble.models import (
    AdvertisementFormat,
    DeviceModel,
    EvidenceLevel,
    Measurement,
    MeasurementKind,
    Reading,
    Unit,
)

T_AND_D_COMPANY_ID = 0x0392
"""Bluetooth SIG company identifier assigned to T&D."""

_COMPANY_ID_BYTES = T_AND_D_COMPANY_ID.to_bytes(2, "little")
_INVALID_VALUE_THRESHOLD = 20_000


@dataclass(frozen=True, slots=True)
class _ModelSpec:
    model: DeviceModel
    packet_format: AdvertisementFormat
    minimum_length: int
    decode: Callable[[bytes], tuple[Measurement, ...]]
    evidence: EvidenceLevel


def _spec(
    model: DeviceModel,
    packet_format: AdvertisementFormat,
    value_offset: int,
    *channels: MeasurementKind,
    evidence: EvidenceLevel = EvidenceLevel.PUBLISHED,
) -> _ModelSpec:
    minimum_length = value_offset + 2 * len(channels)

    def decode(payload: bytes) -> tuple[Measurement, ...]:
        return tuple(
            _decode_measurement(
                channel,
                kind,
                int.from_bytes(payload[offset : offset + 2], "little"),
            )
            for channel, (kind, offset) in enumerate(
                zip(channels, range(value_offset, minimum_length, 2), strict=True),
                start=1,
            )
        )

    return _ModelSpec(model, packet_format, minimum_length, decode, evidence)


_T = MeasurementKind.TEMPERATURE
_H = MeasurementKind.HUMIDITY

# Packet families retained from independent observations without assigning a
# product model or physical measurement. This records provenance without
# turning room inventory into an unconditional protocol mapping.
_OBSERVED_FAMILIES = frozenset({0xC3})

# Serial-family mapping and offsets for TR4/TR4A are published by T&D in its
# M5Stick BLE example. Offsets here exclude the two-byte company identifier,
# matching Bleak's manufacturer_data mapping.
_MODEL_SPECS: dict[int, _ModelSpec] = {
    0x2C: _spec(DeviceModel.TR41, AdvertisementFormat.TR4, 6, _T),
    0x2D: _spec(DeviceModel.TR41, AdvertisementFormat.TR4, 6, _T),
    0x2E: _spec(DeviceModel.TR42, AdvertisementFormat.TR4, 6, _T),
    0x2F: _spec(DeviceModel.TR42, AdvertisementFormat.TR4, 6, _T),
    0x30: _spec(DeviceModel.TR45, AdvertisementFormat.TR4, 6, _T),
    0x31: _spec(DeviceModel.TR45, AdvertisementFormat.TR4, 6, _T),
    0x40: _spec(DeviceModel.TR41A, AdvertisementFormat.TR4A, 8, _T),
    0x41: _spec(DeviceModel.TR41A, AdvertisementFormat.TR4A, 8, _T),
    0x42: _spec(DeviceModel.TR42A, AdvertisementFormat.TR4A, 8, _T),
    0x43: _spec(DeviceModel.TR42A, AdvertisementFormat.TR4A, 8, _T),
    0x44: _spec(DeviceModel.TR43A, AdvertisementFormat.TR4A, 8, _T, _H),
    0x45: _spec(DeviceModel.TR43A, AdvertisementFormat.TR4A, 8, _T, _H),
    0x46: _spec(DeviceModel.TR32B, AdvertisementFormat.TR4A, 8, _T, _H),
    0x47: _spec(DeviceModel.TR32B, AdvertisementFormat.TR4A, 8, _T, _H),
}


def _decode_measurement(channel: int, kind: MeasurementKind, raw: int) -> Measurement:
    value = None if raw > _INVALID_VALUE_THRESHOLD else (raw - 1_000) / 10.0
    unit = Unit.CELSIUS if kind is MeasurementKind.TEMPERATURE else Unit.PERCENT_RH
    return Measurement(channel=channel, kind=kind, value=value, unit=unit, raw_value=raw)


def decode_advertisement(
    data: bytes | bytearray | memoryview,
    *,
    identifier: str = "",
    rssi: int | None = None,
    tx_power: int | None = None,
    name: str | None = None,
    observed_at: datetime | None = None,
    company_id_included: bool = False,
) -> Reading:
    """Decode one T&D manufacturer-specific data value.

    Args:
        data: Manufacturer payload. By default this is the value from
            ``AdvertisementData.manufacturer_data[0x0392]``, where Bleak has
            already separated the company ID.
        identifier: Platform BLE identifier (MAC address on most systems,
            CoreBluetooth UUID on macOS).
        rssi: Received signal strength in dBm.
        tx_power: Advertised transmit power in dBm, when present.
        name: Local or cached BLE name.
        observed_at: Time of receipt. Defaults to the current UTC time.
        company_id_included: Set to ``True`` when ``data`` begins with the
            little-endian company identifier bytes ``92 03``.

    Returns:
        An immutable :class:`~ondotori_ble.models.Reading`. Unknown T&D model
        families are returned without measurements.

    Raises:
        NotOndotoriAdvertisementError: The included company ID is not T&D's.
        MalformedAdvertisementError: The serial or expected values are truncated.
    """
    payload = bytes(data)
    if company_id_included:
        if len(payload) < 2:
            message = "manufacturer data is missing its two-byte company identifier"
            raise MalformedAdvertisementError(message)
        if payload[:2] != _COMPANY_ID_BYTES:
            actual = int.from_bytes(payload[:2], "little")
            message = f"expected T&D company ID 0x0392, got 0x{actual:04X}"
            raise NotOndotoriAdvertisementError(message)
        payload = payload[2:]

    if len(payload) < 4:
        message = f"T&D payload needs at least 4 serial bytes; got {len(payload)}"
        raise MalformedAdvertisementError(message)

    serial = int.from_bytes(payload[:4], "little")
    serial_number = f"{serial:08X}"
    family = payload[2]
    spec = _MODEL_SPECS.get(family)
    timestamp = observed_at or datetime.now(UTC)

    if spec is None:
        return Reading(
            identifier=identifier,
            serial_number=serial_number,
            family_code=family,
            model=DeviceModel.UNKNOWN,
            measurements=(),
            rssi=rssi,
            tx_power=tx_power,
            observed_at=timestamp,
            name=name,
            raw_data=payload,
            advertisement_format=AdvertisementFormat.UNKNOWN,
            evidence=(
                EvidenceLevel.OBSERVED if family in _OBSERVED_FAMILIES else EvidenceLevel.UNKNOWN
            ),
        )

    if len(payload) < spec.minimum_length:
        message = (
            f"{spec.model.value} payload needs at least {spec.minimum_length} bytes; "
            f"got {len(payload)}"
        )
        raise MalformedAdvertisementError(message)

    measurements = spec.decode(payload)
    return Reading(
        identifier=identifier,
        serial_number=serial_number,
        family_code=family,
        model=spec.model,
        measurements=measurements,
        rssi=rssi,
        tx_power=tx_power,
        observed_at=timestamp,
        name=name,
        raw_data=payload,
        advertisement_format=spec.packet_format,
        evidence=spec.evidence,
    )


def decode_manufacturer_data(
    manufacturer_data: Mapping[int, bytes],
    *,
    identifier: str = "",
    rssi: int | None = None,
    tx_power: int | None = None,
    name: str | None = None,
    observed_at: datetime | None = None,
) -> Reading | None:
    """Decode T&D data from a Bleak-style manufacturer-data mapping.

    ``None`` is returned when the mapping contains no T&D company entry.
    The remaining keyword arguments attach receipt metadata to the reading.
    """
    payload = manufacturer_data.get(T_AND_D_COMPANY_ID)
    if payload is None:
        return None
    return decode_advertisement(
        payload,
        identifier=identifier,
        rssi=rssi,
        tx_power=tx_power,
        name=name,
        observed_at=observed_at,
    )
