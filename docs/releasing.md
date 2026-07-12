# Release process

## One-time repository setup

1. Create `Ameyanagi/ondotori-ble` and push the `main` branch.
2. Enable GitHub Pages using GitHub Actions as the source.
3. Create protected `testpypi` and `pypi` environments.
4. Register each workflow as a Trusted Publisher on TestPyPI and PyPI.
5. Require the CI checks before merging to `main`.

No long-lived package-index token is stored in the repository.

## Alpha release checklist

1. Confirm the support table matches the actual decoder registry.
2. Confirm all public fixtures are synthetic or explicitly anonymized.
3. Run Ruff, ty, tests, strict docs, `uv build --no-sources`, Twine, and
   wheel-content validation.
4. Install both built artifacts into isolated environments.
5. Update the version and changelog.
6. Run the manual TestPyPI workflow and install that exact release.
7. Create an annotated tag matching the version, such as `v0.1.0a1`.
8. Push the tag; the PyPI workflow verifies that tag and package versions match.
9. Verify the PyPI metadata, documentation links, provenance, and fresh install.

PyPI files are immutable. If an artifact or metadata error escapes, increment
the version rather than attempting to replace an existing file.

## Protocol release checklist

A release that adds a decoder must also verify its model/module provenance,
conversion boundaries, invalid markers, sanitized fixtures, and hardware
behavior. A Bluetooth-capable product is not listed as advertisement-decoded
unless its current-value layout is actually verified.
