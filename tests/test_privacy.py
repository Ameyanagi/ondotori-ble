from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"
PRIVATE_CAPTURE_KEYS = {
    "capture_duration_seconds",
    "captured_at",
    "firmware_revision",
    "gatt",
    "observations",
    "reported_room_models",
    "sessions",
}


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = {key for key in value if isinstance(key, str)}
        for item in value.values():
            keys.update(nested_keys(item))
        return keys
    if isinstance(value, list):
        keys = set()
        for item in value:
            keys.update(nested_keys(item))
        return keys
    return set()


@pytest.mark.parametrize("fixture_path", sorted(FIXTURE_DIRECTORY.glob("*.json")))
def test_public_capture_fixtures_are_declared_synthetic(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text())

    assert fixture["fixture_kind"] == "synthetic"
    assert fixture["identifier"].startswith("synthetic-")
    assert fixture["name"].startswith("synthetic-")
    assert not PRIVATE_CAPTURE_KEYS.intersection(nested_keys(fixture))
