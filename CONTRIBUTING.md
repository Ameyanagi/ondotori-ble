# Contributing

See the complete [contribution guide](docs/contributing.md).

```console
uv sync --all-groups
lefthook install
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv run --group docs mkdocs build --strict
uv build --no-sources
```

Device-support changes require a public source or independently collected,
sanitized evidence. Never commit a private hardware identifier or restricted
T&D specification.
