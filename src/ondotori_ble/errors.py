"""Exception hierarchy for :mod:`ondotori_ble`."""


class OndotoriError(Exception):
    """Base class for all library-specific exceptions."""


class MalformedAdvertisementError(OndotoriError, ValueError):
    """Raised when T&D manufacturer data is too short or structurally invalid."""


class NotOndotoriAdvertisementError(OndotoriError, ValueError):
    """Raised when data explicitly carries a non-T&D Bluetooth company ID."""


class ScannerUnavailableError(OndotoriError, RuntimeError):
    """Raised when the operating system cannot start a BLE scan."""


class ReadingTimeoutError(OndotoriError, TimeoutError):
    """Raised when no matching BLE reading arrives before a requested timeout."""
