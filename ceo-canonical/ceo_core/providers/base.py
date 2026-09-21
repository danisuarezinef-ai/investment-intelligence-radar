"""Compatibility export for provider contracts.

New code should import contracts from ``ceo_core.contracts``.  This module remains so
existing provider plugins do not break during the MVP 0.2 transition.
"""

from ceo_core.contracts import (  # noqa: F401
    FixedWorkerRouter,
    ProviderHealth,
    WorkerKind,
    WorkerProvider,
    WorkerRequest,
    WorkerResult,
    WorkerRouter,
)

__all__ = [
    "FixedWorkerRouter",
    "ProviderHealth",
    "WorkerKind",
    "WorkerProvider",
    "WorkerRequest",
    "WorkerResult",
    "WorkerRouter",
]
