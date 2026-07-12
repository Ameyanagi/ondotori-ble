# Contributing

## Set up

```console
uv sync --all-groups
lefthook install
```

Install Lefthook using its [official installation instructions](https://lefthook.dev/installation/)
if it is not already available.

## Quality checks

```console
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv run --group docs mkdocs build --strict
uv build --no-sources
```

The pre-commit hook runs Ruff and ty. The pre-push hook runs tests, builds the
strict documentation, and builds the source and wheel distributions.

## Adding a packet family

Do not identify bytes only because they produce plausible numbers. A decoder
change should include:

1. a raw manufacturer payload fixture;
2. the logger model and printed serial number;
3. a simultaneous display/reference measurement when possible;
4. repeated observations showing the expected bytes change; and
5. firmware and input-module/mode information; and
6. a public source or explicit evidence level.

Published T&D layouts use `EvidenceLevel.PUBLISHED`. Reverse-engineered layouts
must use `EvidenceLevel.OBSERVED` and document unknown fields. Uninterpreted
families use `EvidenceLevel.UNKNOWN`.

Original captures containing serials, BLE identifiers, names, or firmware stay
under the ignored `local/captures/` directory. Public fixtures must be synthetic
or explicitly anonymized and must say which they are. Never commit a restricted
T&D communication specification.
