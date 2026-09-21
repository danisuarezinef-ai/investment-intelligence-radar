from __future__ import annotations
import json
from ceo_core.cognitive_evolution import EarlyAbortEngine
from ceo_core.continuity_policy import should_override_cognitive_early_abort
from ceo_core.models import ProjectState, Task, TaskStatus

CANDIDATE = '1.4.89-rc1-continuity-loop-breaker'

def main() -> int:
    state = ProjectState(goal='continuity loop regression')

    internal = Task(
        title='Continuity recovery: independently verify the new result against the locked goal [cycle 1]',
        status=TaskStatus.RETRY,
        metadata={'continuity_gap_recovery': True, 'task_kind': 'verification', 'failure_count': 7, 'strategy_observations': 5},
    )
    state.tasks[internal.id] = internal; state.root_task_ids.append(internal.id)
    abort = EarlyAbortEngine().evaluate(state, internal, spent_fraction=.8, progress_gain=0.0, failure_count=7, expected_success=.1)

    normal = Task(title='Normal productive implementation', status=TaskStatus.RETRY, metadata={'failure_count': 7, 'strategy_observations': 5})
    state.tasks[normal.id] = normal; state.root_task_ids.append(normal.id)
    normal_abort = EarlyAbortEngine().evaluate(state, normal, spent_fraction=.8, progress_gain=0.0, failure_count=7, expected_success=.1)

    protected = Task(
        title='Continuity recovery: publish external release',
        status=TaskStatus.RETRY,
        metadata={'continuity_gap_recovery': True, 'task_kind': 'verification', 'external_action': True, 'strategy_observations': 5},
    )
    state.tasks[protected.id] = protected; state.root_task_ids.append(protected.id)

    checks = {
        'internal_abort_detected': abort['abort'] and abort['reason'] == 'repeated_failures',
        'internal_abort_overridden': should_override_cognitive_early_abort(state, internal),
        'normal_productive_abort_not_overridden': normal_abort['abort'] and not should_override_cognitive_early_abort(state, normal),
        'protected_internal_action_not_overridden': not should_override_cognitive_early_abort(state, protected),
    }
    ok = all(checks.values())
    print(json.dumps({'ok': ok, 'candidate': CANDIDATE, 'checks': checks}, indent=2, sort_keys=True))
    return 0 if ok else 1

if __name__ == '__main__':
    raise SystemExit(main())
