from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RuntimePolicy:
    stage: str = "M02"
    task_execution_enabled: bool = False
    background_execution_enabled: bool = False
    updater_activation_enabled: bool = False
    physical_installation_allowed: bool = False

def policy() -> RuntimePolicy:
    return RuntimePolicy()
