# SciHarness Loop

Optional, separately installed research execution for SciHarness 0.8. Core keeps
its original scientific objects, dependencies, scaffold, CLI, and record-only
behavior. Existing projects need no migration. Loop 0.2 adds configurable Codex
and DeepSeek backends, bounded autonomous runs, and scheduled execution windows.
Nothing starts until explicitly authorized.

## Installation and backend selection

Requires Python 3.10+, POSIX file locking, and a local Docker daemon at
`/var/run/docker.sock`. Harness adapters and execution runtimes are separate;
this release supplies the Docker runtime on Linux/macOS, not Windows or Slurm.
There is no unsandboxed host fallback. From a repository checkout:

```bash
python -m pip install . ./extensions/sciharness-loop
```

Build one of the provided images (or a reviewed derivative with your analysis
libraries). The launcher never pulls images implicitly:

```bash
# Codex: select a reviewed CLI version explicitly.
export CODEX_VERSION='REPLACE_WITH_REVIEWED_VERSION'
docker build --build-arg CODEX_VERSION="$CODEX_VERSION" \
  -t sciharness-codex:local extensions/sciharness-loop

# DeepSeek: standard-library tool harness; no provider SDK dependency.
docker build -f extensions/sciharness-loop/Dockerfile.deepseek \
  -t sciharness-deepseek:local extensions/sciharness-loop
```

Inside a research project, create `.sci/loop/policy.yaml`. Existing v0.1 policies
remain valid and default to the Codex backend. A minimal DeepSeek policy is:

```yaml
schema_version: 1
mode: step
backend: deepseek
runtime: docker
image: sciharness-deepseek:local
model: REPLACE_WITH_SELECTED_MODEL
read_files: [docs/CHARTER.md, docs/STATE.md]
timeout_seconds: 600
```

For Codex, use `backend: codex` and the Codex image; `model` is optional and can
select a specific model. DeepSeek requires an explicit model. Its optional
`base_url` defaults to `https://api.deepseek.com`; HTTPS is required except for
loopback HTTP fixtures. See [policy.example.yaml](policy.example.yaml) for all
common limits. Pin image digests when approval must remain stable across builds;
each actual image ID and launch is recorded in `executor.json`.

Provide `CODEX_API_KEY` or `DEEPSEEK_API_KEY` through the invocation's environment
or your worker's secret manager. Only the selected adapter's credential is
forwarded. Credentials are never written to policy/checkpoints/launch arguments;
research code inside that container can read its provider credential. No host
home, saved CLI auth, other service credentials, or Docker config is mounted.
There is no credential proxy in this release.

| Mode | Authority |
| --- | --- |
| `record_only` (default without a policy) | Read Loop status; use ordinary Core commands |
| `suggest` | Propose one bounded action |
| `step` | Approve one action, then separately review/accept its result |
| `guarded_auto` | Authorize a bounded objective; run multiple exploratory cycles; review results afterwards |

Unknown policy fields, unsupported backends/runtimes, and unavailable enforcement
capabilities fail closed. A mode never starts work by itself.

## Manual plan, step, and acceptance

```bash
sci-loop plan --task "Inspect coverage assumptions with one small diagnostic pilot" --json
# Inspect the actual proposed task, rationale, and review_hash.
sci-loop step --plan <plan-id> --review-hash <plan-hash> --by "Researcher" --json
sci-loop status <step-id> --json
# Review proposal.md, exact scripts/commands, checks, failures, and raw evidence.
sci-loop step --accept <step-id> --review-hash <result-hash> --by "Reviewer" --json
sci validate --json
```

Before acceptance, results stay `pending_review`. Acceptance calls public
`sci new exploration`, so Core allocates the scientific ID, appends the reviewed
narrative to that new Exploration, and copies evidence under
`outputs/explorations/X###/loop-<step-id>/`. Existing scientific records,
CHARTER, STATE, frozen experiments, decisions, and figure approvals have no
automatic mutation capability. Approval identities are operator-provided audit
annotations, not authenticated signatures. Structural validation does not
establish scientific validity.

A completed result can be accepted after switching `guarded_auto` back to `step`
(the normal safety action after an autonomous run). Acceptance reviews evidence
already produced under the recorded execution policy, so the current policy is
not compared again. `record_only` remains read-only: use `step` (or
`guarded_auto`) to accept results, then switch to `record_only` if desired.

## Budgeted runs and overnight scheduling

Set `mode: guarded_auto` explicitly. Create a run specification using
[run.example.yaml](run.example.yaml). For example:

```yaml
schema_version: 1
objective: Investigate coverage-filter sensitivity on the authorized pilot subset.
constraints:
  - Preserve failed checks and exact commands.
  - Request approval if a new dataset or formal experimental design is needed.
runtime_seconds: 28800
max_cycles: 12
timezone: Asia/Shanghai
start_at: '2026-10-22T18:00:00'
end_at: '2026-10-23T08:00:00'
stop_margin_seconds: 60
```

Replace the dates for the intended **one night**. Naive local timestamps use the
IANA timezone; explicit offsets are accepted. Ambiguous DST times require an
explicit offset, and nonexistent local times are rejected. `end_at` must name
the following date for an overnight window. There is no implicit daily replay.
Omit start/end times for an immediate run controlled by its cumulative budget.

```bash
# Prepare only: freeze the specification, selected input identity, and policy.
sci-loop run --spec overnight.yaml --json
# Review scope/limits, then authorize this exact mandate once.
sci-loop run --start <mission-id> --review-hash <mission-hash> --by "Researcher" --json
sci-loop status --mission <mission-id> --json
sci-loop status --missions --json
```

If due now, the approved run executes in the foreground. If its start is in the
future, approval stores a scheduled run and returns without calling a model.
Configure your existing research-server scheduler to invoke this command at the
start time, or periodically with at most one dispatcher per project:

```bash
/absolute/path/to/venv/bin/sci-loop run --dispatch --path /absolute/path/to/study --json
```

The worker must have Docker and the selected provider credential available in
its environment. SciHarness does not install cron jobs, services, or ChatGPT
reminders. Dispatch executes only due, previously approved runs; an expired
window launches no model. Multiple dispatchers cannot acquire the project lock
concurrently, and completed runs are not replayed. Dispatch continues past a
failed mission and reports it under `errors`, so later due missions are still
attempted.

Each cycle creates a fresh bounded plan, then executes one exploratory action.
The planner can stop or request additional approval. A `needs_approval` plan ends
the mission; prepare a new run with the revised objective/constraints (it cannot
be resumed). The planner sees selected, immutable project inputs plus bounded
excerpts/whole artifacts from up to three prior cycles; omitted evidence remains
on disk. Results stay staged for review, not automatically accepted. This version
authorizes adaptive diagnostics and pilot computations; starting/changing formal
experiments and scientific conclusions remains a human-led Core workflow.

`runtime_seconds` is cumulative action/runtime wall time, including planning and
cleanup, not CPU/GPU hours or time spent waiting for a scheduled start/pause.
Mission preparation/input copying and report generation happen outside the
action timer and are not charged. Every action receives the minimum of its
per-action timeout, remaining run budget, and absolute window time. Stop margins
prevent new actions near either boundary. Time/cycle limits, exhausted scope,
failures, or a pause request stop the loop. There is no token/spend cap; provider
usage is logged when available.

A per-action runtime reservation is saved **before** execution. If a controller
crashes, the unconfirmed reservation remains charged; resuming never resets the
budget or silently replays the lost action. A separate host deadline supervisor
is armed before the container starts. It survives controller death and removes
the container at its deadline. Docker/host failure still requires recovery;
the supervisor cannot enforce a deadline while the machine or daemon is down.

Approval also resolves the policy image tag to an immutable image ID and records
`approved_image_id`. Dispatch resolves it again; if the tag now points to a
different image, the mission becomes `needs_approval` instead of running. Pin an
image digest in the policy when a scheduled approval must be stable across
rebuilds.

The preliminary morning report is `.sci/loop/missions/<id>/report.md`. It lists
completed/failed actions, stop reason, consumed/reserved budget, evidence paths,
and agent-reported findings. It is a snapshot written on mission state changes,
not refreshed when a step is later accepted. Review individual step outputs with
the usual `step --accept` command; switching `guarded_auto` to `step` first is
supported. Results from the same mission can be accepted in sequence; unrelated
project/context changes still invalidate approval.

## Pause, recovery, and resumption

```bash
sci-loop run --pause <mission-id> --json
sci-loop run --recover <unfinished-mission-id> --json
sci-loop run --resume <paused-or-failed-id> --review-hash <mission-hash> --by "Researcher" --json
```

Pause signals are outside the agent container and are observed during active
execution. Recovery confirms orphaned actions are stopped, retains partial
files and reservations, and pauses the mission. Resumption requires another
explicit approval of the unchanged scope and its remaining budget. A changed
policy/input/context, an expired window, or a changed resolved image requires a
new run. Pending scientific approval is not silently bypassed by resuming.

The original single-action recovery remains available:

```bash
sci-loop step --recover <unfinished-action-id> --json
sci-loop step --plan <plan-id> --retry-of <failed-step-id> \
  --review-hash <plan-hash> --by "Researcher" --json
```

A partially completed acceptance resumes with the same `step --accept` command
and reuses its ID. It refuses to overwrite edited promoted evidence. To abandon
that partial acceptance, `step --recover` retains the partial Exploration for
manual review. Acceptance is journaled, not a filesystem-wide transaction.

## Isolation, large datasets, and provenance

Docker supplies a read-only root filesystem and selected copied inputs, one
writable action output directory, temporary storage, dropped capabilities, no
privilege escalation, and PID/RAM/CPU limits. No live project, controller state,
Git metadata, host home, or Docker socket is mounted. The agent never executes
code on the host. Containers are created and recorded before they are started.
Only reviewed ordinary files can be promoted; symlinks, FIFOs, devices, traversal,
invalid schemas, and oversized artifact collections are rejected.

Large datasets can be explicitly mounted without copying them into prompts:

```yaml
read_mounts:
  pilot: data/monocyte_subset
```

The source must be beneath the project's `data/` directory and have no symlink
path components. It appears read-only as `/datasets/pilot` for either backend.
Use immutable dataset snapshots. The controller records source path/root stat
identity; it does **not recursively hash a large mounted directory**. Core's
dataset registry and declared dataset hashes remain the scientific provenance.
An external dataset can be staged/bind-mounted beneath `data/` by the operator.

`network: bridge` allows model/literature access; `none` is useful for offline
fixtures. Host networking is forbidden. This is filesystem containment, not
network egress filtering. Output byte/file limits apply at collection, not as
live disk quotas. GPU allocation and other execution runtimes are not exposed
by this release; unsupported options are rejected.

Checkpoints, exact selected inputs, prompts, transcripts, launch metadata, and
all successful/failed artifacts live under `.sci/loop/`. Its local run state is
Git-ignored automatically while `policy.yaml` stays trackable. `status` is
write-free and requires neither Docker nor API access. Nothing is deleted on
uninstall or policy disablement. Back up retained execution evidence separately.

## Adapter/runtime contract and verification

The controller selects a `HarnessAdapter` and `ExecutionRuntime`. Adapters own
commands, model options, and credential names. Runtimes own containment, read-only
mounts, stop, deadlines, and resource enforcement. Codex uses its CLI; DeepSeek
uses the bundled text-file/shell tool loop through the documented Chat Completions
protocol. The DeepSeek adapter is a direct API tool loop, not the DSH harness; a
DSH integration would be a separate `HarnessAdapter` (the controller/runtime
boundary is reusable). Both supplied adapters produce the same result schemas and
use the same review gates.
The `CodexExecutor` facade remains for existing integrations. Default v0.1
policy fingerprints remain valid when new options retain their defaults.

Portable research state is stored in SciHarness files rather than vendor
conversation sessions. Switching a backend/model/runtime changes the policy and
requires new authorization; it never silently changes a running mission.

```bash
python -m pip install -e '.[dev]' -e ./extensions/sciharness-loop
python -m ruff check src tests extensions/sciharness-loop
python -m pytest -q
python -m pytest -q extensions/sciharness-loop/tests
SCI_LOOP_TEST_DOCKER=1 python -m pytest -q extensions/sciharness-loop/tests/test_docker.py
```

Tests cover both adapters against common controller contracts, the production
DeepSeek tool loop over a local HTTP fixture, policy/input integrity, cumulative
budgets, overnight/DST windows, interruption/reservations, review, and packaging.
Mandatory CI Docker tests exercise both backends, read-only mounts, symlink
rejection, a bounded cycle, and stopping a live container after controller death.
No live provider calls or real API keys are used in CI. Actual model behavior
still requires an operator-configured smoke test.

Primary protocol references: [Codex non-interactive execution](https://developers.openai.com/codex/noninteractive/),
[DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/), and
[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/).
