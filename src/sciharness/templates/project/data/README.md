# Data

Raw and derived data are registered in `registry.yaml`. Keep large data files
out of Git; record their location, provenance, and a checksum here or in the
registry instead.

The registry is structurally enforced by `sci validate`:

- `id` must look like `DS###` and be unique;
- `name` is required;
- `storage: local` (default) requires a project-relative `path` that exists;
- `storage: external` requires a `uri`;
- `sha256` is optional and is checked by `sci validate --verify-hashes`;
- `acquired` (or legacy `created`) is an optional ISO date.

Experiments reference datasets with `datasets: [DS001]` in `README.md`, or
`sci new experiment ... --dataset DS001`. `sci validate` checks that every
referenced dataset is declared here.
