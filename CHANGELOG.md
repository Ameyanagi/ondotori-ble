# Changelog

All notable changes are documented here. The project follows Semantic
Versioning after `1.0.0`; pre-1.0 releases may refine the API when documented in
this file.

## [Unreleased]

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

[Unreleased]: https://github.com/Ameyanagi/ondotori-ble/compare/v0.1.0a1...HEAD
[0.1.0a1]: https://github.com/Ameyanagi/ondotori-ble/releases/tag/v0.1.0a1
