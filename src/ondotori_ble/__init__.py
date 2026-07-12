"""Read current T&D Ondotori sensor values from BLE advertisements."""

from importlib.metadata import PackageNotFoundError, version

from ondotori_ble.errors import (
    MalformedAdvertisementError,
    NotOndotoriAdvertisementError,
    OndotoriError,
    ReadingTimeoutError,
    ScannerUnavailableError,
)
from ondotori_ble.models import (
    AdvertisementFormat,
    DeviceModel,
    EvidenceLevel,
    Measurement,
    MeasurementKind,
    Reading,
    Unit,
)
from ondotori_ble.parser import (
    T_AND_D_COMPANY_ID,
    decode_advertisement,
    decode_manufacturer_data,
)
from ondotori_ble.scanner import (
    OndotoriScanner,
    ScannerBackend,
    ScannerFactory,
    ScannerState,
    ScannerStats,
    read,
    read_all,
    read_all_async,
    read_async,
    scan,
    scan_async,
    stream_readings,
)

try:
    __version__ = version("ondotori-ble")
except PackageNotFoundError:  # Source-tree import without installation.
    __version__ = "0+unknown"

__all__ = [
    "T_AND_D_COMPANY_ID",
    "AdvertisementFormat",
    "DeviceModel",
    "EvidenceLevel",
    "MalformedAdvertisementError",
    "Measurement",
    "MeasurementKind",
    "NotOndotoriAdvertisementError",
    "OndotoriError",
    "OndotoriScanner",
    "Reading",
    "ReadingTimeoutError",
    "ScannerBackend",
    "ScannerFactory",
    "ScannerState",
    "ScannerStats",
    "ScannerUnavailableError",
    "Unit",
    "__version__",
    "decode_advertisement",
    "decode_manufacturer_data",
    "read",
    "read_all",
    "read_all_async",
    "read_async",
    "scan",
    "scan_async",
    "stream_readings",
]
