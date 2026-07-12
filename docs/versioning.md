# Versioning and compatibility

The project uses Semantic Versioning. Until `1.0.0`, releases are explicitly
experimental and may make documented API corrections between minor versions.

After `1.0.0`:

- patch releases fix defects without intentional public API breaks;
- minor releases add backward-compatible features and protocol decoders; and
- major releases may remove deprecated behavior.

Only names exported from `ondotori_ble` are public. A public deprecation will be
documented in the changelog and retained for at least one minor release unless
keeping it would create a security or data-correctness problem.

Protocol support is versioned separately in the support matrix: enum membership
does not promise that a model or every input mode is decoded. Applications
should inspect `Reading.is_decoded` and `Reading.evidence`.
