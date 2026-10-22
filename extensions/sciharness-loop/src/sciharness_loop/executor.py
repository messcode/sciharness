"""Compose a replaceable harness adapter and an enforcing execution runtime."""
from __future__ import annotations

from typing import Protocol

from .adapters import CodexAdapter, adapter_for
from .policy import dataset_mounts
from .runtime import DockerRuntime, REQUIRED_CAPABILITIES
from .storage import LoopError


class Executor(Protocol):
    """The controller always calls stop, including after an execution failure."""
    def execute(self, run_id, inputs, work, log, policy): ...

    def stop(self, run_id): ...

    def resolve_image(self, policy): ...


class HarnessExecutor:
    def __init__(self, adapter, runtime, root=None):
        if not REQUIRED_CAPABILITIES <= runtime.capabilities:
            raise LoopError("runtime cannot enforce required isolation/stop/deadline capabilities")
        self.adapter, self.runtime, self.root = adapter, runtime, root

    def resolve_image(self, policy):
        return self.runtime.resolve_image(policy)

    def execute(self, run_id, inputs, work, log, policy):
        if policy.read_mounts and self.root is None:
            raise LoopError("dataset mounts require an explicit project root")
        self.runtime.mounts = dataset_mounts(self.root, policy) if policy.read_mounts else {}
        return self.runtime.execute(run_id, inputs, work, log, policy,
                                    self.adapter.invocation(policy))

    def stop(self, run_id):
        return self.runtime.stop(run_id)


class CodexExecutor(HarnessExecutor):
    """Compatibility facade for existing v0.1 integrations."""
    def __init__(self, root=None):
        super().__init__(CodexAdapter(), DockerRuntime(), root)

    @property
    def docker(self):
        return self.runtime.docker

    def command(self, run_id, inputs, work, policy):
        return self.runtime.command(run_id, inputs, work, policy, self.adapter.invocation(policy))

    def start_command(self, container_id):
        return self.runtime.start_command(container_id)


def make_executor(policy, root=None):
    if policy.runtime != "docker":
        raise LoopError("unsupported execution runtime: " + str(policy.runtime))
    return HarnessExecutor(adapter_for(policy.backend), DockerRuntime(), root)
