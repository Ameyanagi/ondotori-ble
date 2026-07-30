# Changelog

All notable changes are documented here. The project follows Semantic
Versioning after `1.0.0`; pre-1.0 releases may refine the API when documented in
this file.

## [Unreleased]

## [0.1.0] - 2026-07-30

### Changed

- Promote the hardware-validated alpha series to the first stable package
  release and remove prerelease-only installation instructions.

## [0.1.0a3] - 2026-07-30

### Added

- Identify family `C3` as RTR505B from label-verified hardware and decode the
  observed temperature mode used by K-thermocouple and Pt inputs.

## [0.1.0a2] - 2026-07-30

### Added

- `Reading.product_name` and `as_dict()["product_name"]` for the verified
  product name, with explicit TR42A detection coverage.

### Changed

- Added a runnable async README example and clarified that raw family `C3`
  retention does not constitute RTR505B model or measurement support.

## [0.1.0a1] - 2026-07-12

### Added

- Typed sync and async APIs for one-shot and continuous BLE advertisement reads.
- Published TR41/42/45, TR41A/42A/43A, and TR32B current-value decoders.
- Raw retention for observed and unknown T&D packet families.
- Scanner health, bounded backpressure, statistics, and managed server streaming.
- Ruff, ty, pytest, Hypothesis, Lefthook, MkDocs, and release automation.

### Security

- Real room identifiers and packets are excluded from tracked fixtures and
  distributions; the public C3 fixture is explicitly synthetic.

[Unreleased]: https://github.com/Ameyanagi/ondotori-ble/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Ameyanagi/ondotori-ble/compare/v0.1.0a3...v0.1.0
[0.1.0a3]: https://github.com/Ameyanagi/ondotori-ble/compare/v0.1.0a2...v0.1.0a3
[0.1.0a2]: https://github.com/Ameyanagi/ondotori-ble/compare/v0.1.0a1...v0.1.0a2
[0.1.0a1]: https://github.com/Ameyanagi/ondotori-ble/releases/tag/v0.1.0a1
