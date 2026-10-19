# CLI reference

The `sci` CLI performs deterministic bookkeeping, navigation, validation, and
release checks. It never performs scientific interpretation.

## Common options

- `--path DIR` — project directory; defaults to the current directory and
  searches upwards for `.sci.yaml`.
- `--json` — emit one machine-readable object with a stable `schema_version`.
- `--version` — print the installed package version.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | success |
| `1` | validation failure (records, structure, or release readiness) |
| `2` | command-line usage error (from argparse) |
| `3` | project/config error (missing project, bad reference, invalid state) |

### JSON envelope

```json
{
  "schema_version": 1,
  "command": "context",
  "ok": true,
  "project": {"root": "/path/to/project", "name": "My Study"},
  "read_first": ["docs/CHARTER.md", "docs/STATE.md"],
  "active": {"questions": [], "explorations": [], "experiments": []},
  "recent_decisions": [],
  "guidance": [],
  "diagnostics": []
}
```

Command-specific fields sit next to `command`/`ok`. `diagnostics` entries have:

```json
{
  "code": "NOT_FOUND",
  "severity": "error",
  "message": "paths.state does not exist: docs/STATE.md",
  "path": ".sci.yaml",
  "hint": "..."
}
```

`path`, `field`, and `hint` are optional. Errors in JSON mode still emit JSON
and use exit code `3`.

## Commands

### `sci init TARGET [--name NAME] [--no-git] [--json]`

Create a new independent project from the bundled scaffold. `TARGET` must be
absent or empty. The command fills the project name/date, creates tracked
directories with `.gitkeep`, deploys the packaged Skills, writes `.sci.yaml` and
`.sci/scaffold.json`, and initializes a fresh Git repository with one root
commit.

```bash
sci init my-study --name "My Study"
```

### `sci status [--path DIR] [--json]`

Summarize active questions, explorations, experiments, recent decisions,
manuscript figures, and validation state. Returns `1` when validation reports
problems.

### `sci context [--path DIR] [--json]`

Deterministic agent bootstrap:

- files to read first (charter, state);
- active records;
- recent decisions;
- conditional guidance;
- diagnostics, including `STATE_STALE` when `docs/STATE.md` predates the newest
  record.

Returns `1` only when diagnostics contain errors.

### `sci show ID [--related] [--path DIR] [--json]`

Resolve `Q###`, `X###`, `EXP###`, or `D###` to its canonical record path and
output workspace. `--related` adds incoming references:

```text
Referenced by:
  D001  [decision]  Product law weakened  (evidence)
  EXP001  [experiment]  Second-order forcing  (exploration)
```

JSON includes `record.references` (outgoing) and `record.backlinks` (incoming).

### `sci new ...`

```bash
sci new question "What predicts R_k(t)?"
sci new exploration "Inspect early trajectory" --question Q001
sci new experiment "Test accumulated forcing" \
  --question Q001 --exploration X001 --dataset DS001
sci new decision "Revise the working hypothesis" \
  --question Q001 --evidence X003 --evidence EXP007
```

IDs are allocated by the CLI. The experiment `--dataset DS###` flag is
repeatable and requires the dataset to be declared in `data/registry.yaml`.

### `sci start EXP### [--path DIR] [--json]`

Move a planned experiment to `running`, freeze its pre-registration hash, and
create/update `experiments/EXP###/run.yaml`. Only `planned` experiments can be
started.

### `sci validate [--verify-hashes] [--path DIR] [--json]`

Check configuration, paths, front matter, IDs, references, dataset registry,
experiment `config.yaml`, `run.yaml`, and pre-registration hashes.
`--verify-hashes` also recomputes declared local dataset SHA-256 values.

### `sci figure ...`

```bash
sci figure init figure3
sci figure validate figure3
sci figure approve figure3 --by "Reviewer Name"
sci figure validate figure3 --release
```

- `init` creates `FIGURE.md`, `manifest.yaml`, `working/`, `previews/`, and
  `release/`. Release subdirectories are declared by the manifest, not imposed.
- `approve` requires `status: validated`, at least one declared release output,
  and writes `release/APPROVAL.yaml` with review hashes.
- `validate --release` accepts `status: validated` or `released`, requires
  approval, verifies hashes, and checks declared artifacts/source data.

### `sci figure init/approve/validate --json`

Returns `figure.init`, `figure.approve`, or `figure.validate` envelopes with
figure-specific fields and diagnostics.

### `sci doctor [--fix] [--path DIR] [--json]`

Diagnose validation problems, scaffold drift, and unclaimed record IDs.
`--fix` backfills missing ID claims and adopts a missing scaffold baseline.
Returns `1` only when there are error diagnostics.

### `sci upgrade [--dry-run] [--force] [--path DIR] [--json]`

Update managed scaffold files (project templates and deployed Skills):

- files whose current hash still matches `.sci/scaffold.json` are updated;
- locally modified files are preserved and receive a `.new` sidecar;
- `--force` overwrites local edits;
- `--dry-run` previews actions.

### `sci migrate [--dry-run] [--path DIR] [--json]`

Apply sequential migrations to `.sci.yaml` only. Records, figures, and scaffold
files keep their own `schema_version` and are handled by `sci upgrade`.
A newer-than-supported schema is refused.

### `sci --version`

Print `sci <version>`.
