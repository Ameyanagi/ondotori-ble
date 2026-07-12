from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ondotori_ble.models import (
    AdvertisementFormat,
    DeviceModel,
    EvidenceLevel,
    Measurement,
    MeasurementKind,
    Reading,
    Unit,
)


def make_reading(**changes: object) -> Reading:
    values: dict[str, object] = {
        "identifier": "id",
        "serial_number": "12345678",
        "family_code": 0x34,
        "model": DeviceModel.TR41,
        "measurements": (),
        "rssi": -50,
        "tx_power": None,
        "observed_at": datetime(2026, 7, 12, tzinfo=UTC),
        "name": None,
        "raw_data": b"1234",
        "advertisement_format": AdvertisementFormat.TR4,
        "evidence": EvidenceLevel.PUBLISHED,
    }
    values.update(changes)
    return Reading(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("channel", [0, -1])
def test_measurement_rejects_invalid_channel(channel: int) -> None:
    with pytest.raises(ValueError, match="channel"):
        Measurement(channel, MeasurementKind.TEMPERATURE, 1.0, Unit.CELSIUS, 1_010)


@pytest.mark.parametrize("raw_value", [-1, 0x1_0000_0000])
def test_measurement_rejects_invalid_raw_value(raw_value: int) -> None:
    with pytest.raises(ValueError, match="32-bit"):
        Measurement(1, MeasurementKind.TEMPERATURE, 1.0, Unit.CELSIUS, raw_value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_measurement_rejects_non_finite_value(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        Measurement(1, MeasurementKind.TEMPERATURE, value, Unit.CELSIUS, 1_010)


def test_measurement_rejects_mismatched_unit() -> None:
    with pytest.raises(ValueError, match="does not match"):
        Measurement(1, MeasurementKind.VOLTAGE, 1.0, Unit.CELSIUS, 1)


@pytest.mark.parametrize("serial", ["123", "nothex!!"])
def test_reading_rejects_bad_serial(serial: str) -> None:
    with pytest.raises(ValueError, match="serial_number"):
        make_reading(serial_number=serial)


def test_reading_requires_timezone_aware_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_reading(observed_at=datetime(2026, 7, 12))  # noqa: DTZ001


@pytest.mark.parametrize("family_code", [-1, 256])
def test_reading_rejects_invalid_family_code(family_code: int) -> None:
    with pytest.raises(ValueError, match="family_code"):
        make_reading(family_code=family_code)


def test_decode_state_depends_on_typed_measurements() -> None:
    undecoded = make_reading()
    decoded = make_reading(
        measurements=(Measurement(1, MeasurementKind.TEMPERATURE, 20.0, Unit.CELSIUS, 1_200),),
    )

    assert not undecoded.is_decoded
    assert decoded.is_decoded
    assert decoded.values(MeasurementKind.TEMPERATURE) == (20.0,)
    assert decoded.first_value(MeasurementKind.TEMPERATURE) == 20.0
    assert decoded.first_value(MeasurementKind.VOLTAGE) is None
