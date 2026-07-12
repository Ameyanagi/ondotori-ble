from __future__ import annotations

from contextlib import suppress

from hypothesis import given
from hypothesis import strategies as st

from ondotori_ble import (
    MalformedAdvertisementError,
    NotOndotoriAdvertisementError,
    decode_advertisement,
)


@given(data=st.binary(max_size=255), company_id_included=st.booleans())
def test_decoder_never_leaks_unexpected_exceptions(
    data: bytes,
    company_id_included: bool,
) -> None:
    with suppress(MalformedAdvertisementError, NotOndotoriAdvertisementError):
        decode_advertisement(data, company_id_included=company_id_included)


@given(
    family=st.sampled_from(
        [0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47]
    ),
    prefix=st.integers(min_value=0, max_value=0xFFFF),
    suffix=st.integers(min_value=0, max_value=0xFF),
    raw_one=st.integers(min_value=0, max_value=0xFFFF),
    raw_two=st.integers(min_value=0, max_value=0xFFFF),
)
def test_published_family_decoder_preserves_identity_and_raw_data(
    family: int,
    prefix: int,
    suffix: int,
    raw_one: int,
    raw_two: int,
) -> None:
    serial = (suffix << 24) | (family << 16) | prefix
    payload = bytearray(18)
    payload[:4] = serial.to_bytes(4, "little")
    offset = 6 if family < 0x40 else 8
    payload[offset : offset + 2] = raw_one.to_bytes(2, "little")
    payload[offset + 2 : offset + 4] = raw_two.to_bytes(2, "little")

    reading = decode_advertisement(payload)

    assert reading.serial == serial
    assert reading.family_code == family
    assert reading.raw_data == payload
