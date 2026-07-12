from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ondotori_ble import (
    T_AND_D_COMPANY_ID,
    AdvertisementFormat,
    DeviceModel,
    EvidenceLevel,
    MalformedAdvertisementError,
    MeasurementKind,
    NotOndotoriAdvertisementError,
    decode_advertisement,
    decode_manufacturer_data,
)


def make_payload(serial: str, value_offset: int, *raw_values: int, length: int = 18) -> bytes:
    payload = bytearray(length)
    payload[:4] = int(serial, 16).to_bytes(4, "little")
    for index, raw_value in enumerate(raw_values):
        offset = value_offset + index * 2
        payload[offset : offset + 2] = raw_value.to_bytes(2, "little")
    return bytes(payload)


@pytest.mark.parametrize(
    ("serial", "offset", "model"),
    [
        ("5F2C0123", 6, DeviceModel.TR41),
        ("5F2D0123", 6, DeviceModel.TR41),
        ("5F2E0123", 6, DeviceModel.TR42),
        ("5F2F0123", 6, DeviceModel.TR42),
        ("5F300123", 6, DeviceModel.TR45),
        ("5F310123", 6, DeviceModel.TR45),
        ("5F400123", 8, DeviceModel.TR41A),
        ("5F410123", 8, DeviceModel.TR41A),
        ("5F420123", 8, DeviceModel.TR42A),
        ("5F430123", 8, DeviceModel.TR42A),
    ],
)
def test_decodes_published_temperature_models(
    serial: str,
    offset: int,
    model: DeviceModel,
) -> None:
    reading = decode_advertisement(make_payload(serial, offset, 1_253))

    assert reading.serial_number == serial
    assert reading.serial == int(serial, 16)
    assert reading.family_code == int(serial[2:4], 16)
    assert reading.model is model
    assert reading.temperature_c == 25.3
    assert reading.temperatures_c == (25.3,)
    assert reading.humidity_percent is None
    assert reading.evidence is EvidenceLevel.PUBLISHED
    expected_format = AdvertisementFormat.TR4 if offset == 6 else AdvertisementFormat.TR4A
    assert reading.advertisement_format is expected_format


@pytest.mark.parametrize(
    ("serial", "model"),
    [
        ("5F440123", DeviceModel.TR43A),
        ("5F450123", DeviceModel.TR43A),
        ("5F460123", DeviceModel.TR32B),
        ("5F470123", DeviceModel.TR32B),
    ],
)
def test_decodes_published_temperature_humidity_models(
    serial: str,
    model: DeviceModel,
) -> None:
    reading = decode_advertisement(make_payload(serial, 8, 1_234, 1_567))

    assert reading.model is model
    assert reading.temperature_c == 23.4
    assert reading.humidity_percent == 56.7
    assert reading.humidities_percent == (56.7,)
    assert [measurement.kind for measurement in reading.measurements] == [
        MeasurementKind.TEMPERATURE,
        MeasurementKind.HUMIDITY,
    ]


def test_observed_c3_family_remains_unidentified() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "observed-c3-synthetic.json"
    fixture = json.loads(fixture_path.read_text())
    observed_at = datetime.fromisoformat(fixture["observed_at"])

    reading = decode_advertisement(
        bytes.fromhex(fixture["manufacturer_data"]),
        identifier=fixture["identifier"],
        rssi=fixture["rssi"],
        name=fixture["name"],
        observed_at=observed_at,
    )

    assert reading.model is DeviceModel.UNKNOWN
    assert reading.advertisement_format is AdvertisementFormat.UNKNOWN
    assert reading.serial_number == fixture["serial_number"]
    assert reading.family_code == 0xC3
    assert reading.measurements == ()
    assert not reading.is_decoded
    assert reading.evidence is EvidenceLevel.OBSERVED
    assert reading.observed_at is observed_at
    assert reading.identifier == fixture["identifier"]
    assert reading.name == "synthetic-c3"


def test_synthetic_c3_samples_preserve_unassigned_candidate_words() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "observed-c3-synthetic.json"
    fixture = json.loads(fixture_path.read_text())

    readings = [
        decode_advertisement(bytes.fromhex(sample["manufacturer_data"]))
        for sample in fixture["samples"]
    ]

    words = [
        [
            int.from_bytes(reading.raw_data[6:8], "little"),
            int.from_bytes(reading.raw_data[8:10], "little"),
        ]
        for reading in readings
    ]

    assert words == [sample["candidate_words"] for sample in fixture["samples"]]
    assert all(reading.measurements == () for reading in readings)
    assert all(reading.evidence is EvidenceLevel.OBSERVED for reading in readings)


def test_adjacent_rtr500b_family_is_not_guessed() -> None:
    reading = decode_advertisement(make_payload("52C20783", 6, 1_073, 1_271))

    assert reading.model is DeviceModel.UNKNOWN
    assert reading.measurements == ()
    assert reading.evidence is EvidenceLevel.UNKNOWN


def test_company_id_can_be_included_in_input() -> None:
    payload = make_payload("5F400123", 8, 1_111)

    reading = decode_advertisement(b"\x92\x03" + payload, company_id_included=True)

    assert reading.temperature_c == 11.1


def test_rejects_wrong_included_company_id() -> None:
    with pytest.raises(NotOndotoriAdvertisementError, match="0x004C"):
        decode_advertisement(b"\x4c\x00payload", company_id_included=True)


@pytest.mark.parametrize("payload", [b"", b"\x92"])
def test_rejects_truncated_included_company_id(payload: bytes) -> None:
    with pytest.raises(MalformedAdvertisementError, match="company identifier"):
        decode_advertisement(payload, company_id_included=True)


@pytest.mark.parametrize("payload", [b"", b"\x01", b"\x01\x02\x03"])
def test_rejects_truncated_serial(payload: bytes) -> None:
    with pytest.raises(MalformedAdvertisementError, match="serial bytes"):
        decode_advertisement(payload)


def test_rejects_truncated_known_packet() -> None:
    with pytest.raises(MalformedAdvertisementError, match="TR43A payload needs"):
        decode_advertisement(make_payload("5F440123", 8, length=9))


def test_unknown_tandd_family_remains_observable() -> None:
    payload = make_payload("12AB3456", 6, 1_200)

    reading = decode_advertisement(payload)

    assert reading.model is DeviceModel.UNKNOWN
    assert reading.measurements == ()
    assert reading.evidence is EvidenceLevel.UNKNOWN
    assert not reading.is_decoded
    assert reading.temperature_c is None


def test_invalid_sensor_marker_is_preserved() -> None:
    reading = decode_advertisement(make_payload("5F440123", 8, 0xEEEE, 0xFFFF))

    assert reading.temperature_c is None
    assert reading.humidity_percent is None
    assert all(not measurement.is_valid for measurement in reading.measurements)
    assert [measurement.raw_value for measurement in reading.measurements] == [0xEEEE, 0xFFFF]


def test_manufacturer_mapping_filters_and_forwards_metadata() -> None:
    assert decode_manufacturer_data({0x004C: b"apple"}) is None
    observed_at = datetime(2026, 7, 12, tzinfo=UTC)
    reading = decode_manufacturer_data(
        {T_AND_D_COMPANY_ID: make_payload("5F400123", 8, 1_250)},
        identifier="device-id",
        rssi=-42,
        tx_power=9,
        name="logger",
        observed_at=observed_at,
    )

    assert reading is not None
    assert reading.identifier == "device-id"
    assert reading.rssi == -42
    assert reading.tx_power == 9
    assert reading.name == "logger"
    assert reading.observed_at is observed_at


def test_reading_as_dict_is_json_serializable() -> None:
    reading = decode_advertisement(make_payload("5F440123", 8, 1_234, 1_567))

    result = reading.as_dict()

    assert json.loads(json.dumps(result))["measurements"][1] == {
        "channel": 2,
        "kind": "humidity",
        "value": 56.7,
        "unit": "%RH",
        "raw_value": 1567,
    }
    assert result["raw_data"] == reading.raw_data.hex()
    assert result["family_code"] == 0x44
    assert result["is_decoded"] is True
