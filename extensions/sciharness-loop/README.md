# SciHarness Loop — human-controlled MVP

An **optional, separately installed** execution layer for SciHarness 0.8.
Core does not import it, install its dependencies, change its scientific object
model, or start it automatically. Uninstalling this package leaves `sci` and all
scientific records usable. Existing projects need no migration.

This version provides `plan`, `step`, and `status`. There is no daemon,
continuous `run`, multi-agent planner, or automatic scientific decision.

## Installation and explicit opt-in

Requires Python 3.10+, POSIX file locking, and a **local Docker daemon** at
`/var/run/docker.sock`. Docker enforces filesystem isolation; a host Codex
fallback is intentionally unavailable. Docker Desktop on macOS is supported
when it exposes that socket. Windows and rootless/custom Docker sockets are
not supported by this MVP.

From a checkout of this repository:

```bash
python -m pip install . ./extensions/sciharness-loop
# Pick and review an exact Codex CLI version before building the image:
export CODEX_VERSION='REPLACE_WITH_REVIEWED_VERSION'
docker build --build-arg CODEX_VERSION="$CODEX_VERSION" \
  -t sciharness-codex:local extensions/sciharness-loop
```

Build the trusted executor image locally. The launcher never pulls an image
implicitly. The supplied image has Codex, Git, and Python; add project-specific
analysis dependencies to your own reviewed image as needed. Pin the image digest
in the policy for repeatable environments.

Inside an existing research project, explicitly create
`.sci/loop/policy.yaml` using [policy.example.yaml](policy.example.yaml).
No policy means `record_only`. Unknown fields, modes, permissions, or unsupported
limits are errors, not silently ignored configuration.

| Mode | Allowed behavior |
| --- | --- |
| `record_only` | Read Loop status; ordinary `sci` commands remain available |
| `suggest` | Ask Codex for one bounded proposed action; no result promotion |
| `step` | Suggest, approve one action, execute it in isolation, review and accept its Exploration |

Provide `CODEX_API_KEY` only in the environment of the invoked `sci-loop`
process, using your usual secret manager. Never put it in policy, project files,
or shell history. This key is passed to the isolated Codex process; research
code in that container can read it. Use trusted tasks/code and a dedicated key.
No host home, saved CLI auth, other service credentials, or Docker config is
forwarded. This MVP does not implement an API credential proxy.

## One complete research cycle

```bash
sci-loop status --json
sci-loop plan --task "Inspect coverage assumptions with one small diagnostic pilot" --json
```

`plan` reads `sci context --json`, the configured charter/state, and only the
explicit `read_files`. It returns an execution ID, a proposed title, task with
completion criteria, rationale, and `review_hash`. Inspect the **actual proposed
task**, not only the original request. Then approve that exact plan:

```bash
sci-loop step --plan <plan-id> --review-hash <plan-review-hash> --by "Researcher" --json
sci-loop status <step-id> --json
```

The result is `pending_review`. Inspect these files under
`.sci/loop/runs/<step-id>/`:

- `input/`: exact selected inputs, public Core context, prompt, and output schema;
- `executor.log`: raw Codex JSON events and stderr, including failures;
- `executor.json`: resolved image ID and exact launch arguments (no credential value);
- `work/proposal.md`: proposed exploratory narrative;
- `work/artifacts/`: scripts, commands, raw checks, and generated outputs;
- `work/result.json`: agent-reported summary, checks, and limitations;
- `checkpoint.json`: policy, approvals, hashes, state history, and provenance.

Review scientific validity, failed checks, and evidence independently. If you
agree to retain the result as an Exploration, approve the **result** hash:

```bash
sci-loop step --accept <step-id> --review-hash <result-review-hash> --by "Reviewer" --json
sci validate --json
```

The controller calls public `sci new exploration`, so Core allocates the `X###`
ID. It appends the reviewed narrative to that new record and copies the reviewed
evidence into `outputs/explorations/X###/loop-<step-id>/`. It never edits an
existing scientific record, CHARTER, STATE, experiment, decision, or figure.
The record title includes the execution ID to make crash recovery unambiguous.

Approval identities are operator-provided audit annotations, not authenticated
signatures. The agent cannot invoke the host controller or access approval
state. Policy, selected input, or artifact changes invalidate stale approval.
Acceptance preserves exploratory evidence; it does **not** establish a scientific
claim or start a formal experiment. `sci validate` remains a structural check.

All commands accept `--path DIR` (searching parents) and `--json`.
JSON uses `schema_version: 1`, `ok`, `command`, and `result` or `error`.
Exit codes are 0 success, 1 policy/project/execution error, and 2 CLI usage error.
`status` has no writes, no API call, and no Docker requirement.

## Isolation and permissions

The trusted controller runs Core's read-only context/validation commands on the
host. Codex runs in a fresh Docker container with:

- a read-only root filesystem and an exact, bounded **copy** of selected inputs;
- one writable per-execution output directory and a bounded temporary filesystem;
- no live-project, host-home, Git metadata, controller-state, or Docker-socket mount;
- dropped capabilities, no privilege escalation, host UID/GID, PID/memory/CPU
  limits, and a wall-clock timeout.

The Codex CLI runs `exec` with JSON events, an output schema, and a fresh session.
Its sandbox mode is `danger-full-access` **inside this dedicated container**;
Docker is the enforcing outer boundary, avoiding nested sandbox incompatibility.
The controller never runs agent-generated scripts on the host. Only ordinary,
reviewed files in `proposal.md`, `result.json`, and `artifacts/` can be promoted;
links, devices, sockets, FIFOs, traversal, excess files, and oversized output
bundles are rejected. Other project mutations have no promotion capability.

The local Docker daemon, image, operator, installed Core, and controller are
trusted. Filesystem containment does not provide network egress filtering.
`network: bridge` enables API/literature access, including access to network
services reachable from the container; `host` networking is forbidden. Use
host/network infrastructure for finer egress rules. Semantic distinctions between
an exploratory analysis and a formal test require scientific human judgment.

Input size is capped in bytes (not an exact token count), and every invocation
uses a fresh bounded context instead of accumulated conversation history. Output
size/count limits apply when collecting/reviewing artifacts; they are **not live
disk quotas**. Runtime, RAM, and CPU are enforced by the executor. This MVP does
not promise token/spend limits or independent verification of model-reported
checks. Provision disk space and inspect transcripts accordingly.

## Checkpoints and recovery

Normal states are `prepared → running → suggested` for a plan and
`prepared → running → pending_review → applying → accepted` for a step.
Failures retain the checkpoint, partial files, prompt, and transcript. An
unconfirmed container stop becomes `recovery_required`, blocking retry until
recovery. Process death may leave `prepared` or `running` on disk.

```bash
sci-loop status --json
# Stop an orphan container and retain its partial evidence:
sci-loop step --recover <unfinished-execution-id> --json
# Explicitly retry a failed/interrupted step in a fresh execution:
sci-loop step --plan <plan-id> --retry-of <failed-step-id> \
  --review-hash <plan-review-hash> --by "Researcher" --json
```

Recovery can stop an orphan even after switching back to `record_only`.
Retry preserves the original failed execution. A changed project needs a new
plan. A checkpoint in `applying` resumes with the same `step --accept` command;
it reuses the allocated ID and refuses to overwrite edited promoted evidence.
Acceptance is journaled, not a transaction across the entire filesystem: a
partially created Exploration can be visible until acceptance resumes. Avoid
editing that record while recovery is pending. Core's ID claims remain permanent.
Selected input/configuration changes also block resumed acceptance. If you need
to abandon a partial acceptance, `step --recover <step-id>` retains its partial
Exploration and evidence for manual review, then permits a new plan. It never
deletes or rolls back scientific records.

The OS lock serializes Loop writers and releases automatically on process
death. It does not lock independent human/Core edits; coordinate those during
acceptance. Checkpoints are atomically replaced and synced. No logs or failed
evidence are automatically deleted. Back up `.sci/loop/` and generated output
bundles as needed; they can contain sensitive selected data and transcripts.
Uninstalling Loop or disabling its policy does not remove these files.

## Development and verification

```bash
python -m pip install -e '.[dev]' -e ./extensions/sciharness-loop
python -m ruff check src tests extensions/sciharness-loop
python -m pytest -q
python -m pytest -q extensions/sciharness-loop/tests
SCI_LOOP_TEST_DOCKER=1 python -m pytest -q extensions/sciharness-loop/tests/test_docker.py
```

Tests use the real public Core CLI for planning context, validation, ID allocation,
promotion, and recovery. Deterministic executor fixtures cover approval binding,
stale inputs/artifacts/policy, timeouts, failed attempts, locks, path escapes,
and resumable promotion. The Docker tests run an adversarial fixture through the
production launcher without a model/API key; CI requires them to run, not skip.
Local runs without Docker explicitly skip those tests. A real model smoke test
requires a built Codex image and operator-provided API access; it is not part of
credential-free CI. Follow the cycle above to perform that acceptance check.

Executor replacement is a small Python `Executor` protocol (`execute`, `stop`),
not an arbitrary host-command CLI option. Future backends must implement an
equivalent enforced isolation boundary before being exposed to users.

Official CLI contract: [non-interactive execution](https://developers.openai.com/codex/noninteractive/)
and [CLI reference](https://developers.openai.com/codex/cli/reference/).
