# SciHarness Loop

Optional, separately installed research execution for SciHarness 0.8. Core keeps
its original scientific objects, dependencies, scaffold, CLI, and record-only
behavior. Existing projects need no migration. Loop 0.2 adds configurable Codex,
DeepSeek, and DSH backends, bounded autonomous runs, and scheduled execution
windows. Nothing starts until explicitly authorized.

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

# DSH: pinned headless bundle; initializes the shipped headless profile.
docker build -f extensions/sciharness-loop/Dockerfile.dsh \
  -t sciharness-dsh:local extensions/sciharness-loop

# Optional MCP: add exactly one pinned server package to the DSH image.
docker build -f extensions/sciharness-loop/Dockerfile.dsh-mcp \
  --build-arg MCP_SERVER_PACKAGE='REPLACE_WITH_PACKAGE' \
  --build-arg MCP_SERVER_VERSION='REPLACE_WITH_VERSION' \
  -t sciharness-dsh-mcp:local extensions/sciharness-loop
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

A minimal DSH policy:

```yaml
schema_version: 1
mode: step
backend: dsh
runtime: docker
image: sciharness-dsh:local
model: deepseek-flash   # optional; omitted uses the DSH profile default
read_files: [docs/CHARTER.md, docs/STATE.md]
timeout_seconds: 600
```

DSH is a profile/bundle harness, not a plain CLI. The `dsh` backend uses the
shipped `headless` one-shot bundle through `dsh_runner.py`. The adapter pins
`DSH_HOME`, uses the launch `DEEPSEEK_API_KEY` (headless deliberately ignores
GUI-saved credentials and the managed store), and sets DSH's
`danger-full-access` permission mode because the Docker container is the
isolation boundary; without it, headless tool calls wait for an approval nobody
can answer. To preserve the Loop's one-bounded-action rule, the wrapper disables
DSH's subagent, workflow, web, background-job, and goal tools; file, shell, skill,
todo, and working-directory tools remain. `base_url` for DSH is the **Messages
API root** (`https://api.deepseek.com/anthropic` by default), not the DeepSeek
Chat Completions root. DSH has no `--model` flag, so the wrapper writes a
`--patch` for `agent-default-model`. The wrapper streams the headless NDJSON
events into `executor.log`, derives `result.json` from the file or the terminal
`final` event, and logs the DSH session id. The image pins
`@deepseek-ai/dsh@0.2.1-rc.2`; a live model smoke test still requires
`DEEPSEEK_API_KEY` and network access. DSH owns its model/context/compaction
settings, so the DeepSeek-only `max_turns`, `max_context_bytes`, and
`max_completion_tokens` limits do not apply to this backend; the per-action
Docker timeout/deadline still does.

Provide `CODEX_API_KEY` or `DEEPSEEK_API_KEY` through the invocation's environment
or your worker's secret manager. Only the selected adapter's credential is
forwarded. Credentials are never written to policy/checkpoints/launch arguments;
research code inside that container can read its provider credential. No host
home, saved CLI auth, other service credentials, or Docker config is mounted.
There is no credential proxy in this release. DSH uses `DEEPSEEK_API_KEY`; its
headless profile intentionally does not consume credentials saved by the DSH GUI.

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

## Project Skills

`skills: [scientific-research, scientific-figures]` selects named read-only
bundles from `<project>/.agents/skills/`. The `sci` scaffold deploys the packaged
Skills there. Selected bundles (including `references/`, `scripts/`, and
`assets/`) are bounded by `max_input_bytes`/`max_files`, copied to
`/input/project/.agents/skills/`, and included in the input/review hash. A skill
change therefore invalidates a pending review; skills are instructions, not
scientific evidence.

DSH discovers them through a `skill-filesystem.customSkillDirs` patch and exposes
them via its native `tool-skill`; Codex and the DeepSeek tool loop can read the
same files through their normal file tools. Skills are read-only in the
container and are never loaded from the host's user-level skill directories.

## MCP (default off)

No MCP server is enabled by the generic DSH image. MCP is opt-in through a
`mcp.servers` policy block and a **separate** `Dockerfile.dsh-mcp` image that
bakes the reviewed, pinned server package. The server runs inside the same
Docker container as DSH; no host MCP configuration, host credentials, or host
processes are used.

Each server is reached through `mcp_proxy.py`. The proxy:

- forwards JSON-RPC to the real stdio server;
- filters `tools/list` to the explicit `tools` allowlist;
- returns an error for any non-allowlisted `tools/call`;
- starts the server with only the named `env` variables and `PATH`/`HOME`;
- never stores credential values in the policy or the proxy config.

The allowlist, command, server name, timeout, and credential variable names are
part of the policy fingerprint and therefore the mission/step approval hash.
Changing any of them requires new authorization. MCP tool results and server
instructions are untrusted input and remain subject to human review. This
release supports **stdio** MCP servers only; Streamable HTTP MCP is not enabled
because the allowlist proxy would need a separate network/transport policy.

A minimal MCP policy (the image and `command` are deployment-specific):

```yaml
mcp:
  servers:
    - name: fixture
      command: [python3, /opt/sciharness/mcp_fixture_server.py]
      tools: [lookup]
      env: [MCP_TOKEN]
      timeout_seconds: 60
```

## Capabilities (default bounded)

Extra agent power is an explicit, approval-hashed opt-in, not a default:

```yaml
capabilities:
  dsh:
    tools: [subagents, workflow, web, jobs, goals]   # default []
    session: action                                  # mission not yet supported
  codex:
    agents_md: true                                  # stage AGENTS.md into /work
    skills: true                                     # stage .agents/skills into /work
```

- DSH tool groups map to its native `tool-subagent*`, `tool-workflow`,
  `tool-web`, `tool-jobs`, and `tool-goal`. The default disables all of them.
- Codex uses `codex_runner.py`: it copies only the reviewed `AGENTS.md` and
  `.agents/skills` from `/input/project` into `/work` before exec'ing Codex. No
  host Codex config, auth, MCP, or user skills are mounted.
- The capability selection is part of `Policy.fingerprint`, so changing it
  requires a new plan/mission approval.
- Mission-scoped DSH sessions and Codex MCP staging are not implemented in this
  version; both fail closed rather than silently using action-scoped behavior.
- The Docker container remains the isolation boundary; enabling subagents/web/
  jobs still consumes the same action timeout, budget, and review gate.

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
protocol; DSH uses the shipped one-shot `headless` bundle through
`dsh_runner.py`. The DeepSeek adapter remains a direct API tool loop (not DSH).
The DSH adapter owns DSH's profile/home, non-interactive permission mode, model
patch, minimal tool surface, NDJSON stream, session logging, and result contract.
All three adapters produce the same result schemas and use the same review gates.
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

Tests cover all three adapters against common controller contracts, the production
DeepSeek tool loop over a local HTTP fixture, the DSH headless wrapper/profile
patch, project-Skill provisioning and review binding, the default-off MCP
allowlist/proxy and DSH patch, opt-in DSH tool groups and Codex project staging,
policy/input integrity, cumulative budgets, overnight/DST windows,
interruption/reservations, review, and packaging. Mandatory CI Docker tests
exercise all three backends, read-only mounts, symlink rejection, a bounded cycle,
and stopping a live container after controller death. A separate CI job builds
`Dockerfile.dsh` and verifies `dsh --version` plus the initialized headless profile
without calling a model. No live provider calls or real API keys are used in CI.
Actual model behavior still requires an operator-configured smoke test.

Primary protocol references: [Codex non-interactive execution](https://developers.openai.com/codex/noninteractive/),
[DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/),
[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/),
and [DSH headless one-shot](https://github.com/deepseek-ai/deepseek-harness).
