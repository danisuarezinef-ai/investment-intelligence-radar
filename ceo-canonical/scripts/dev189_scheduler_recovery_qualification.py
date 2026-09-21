from __future__ import annotations

import json
from ceo_core.autonomous_loop import AutonomousProjectLoop
from ceo_core.completion import CompletionEngine
from ceo_core.models import ProjectState, Task, TaskStatus


def domain(title: str, status: TaskStatus) -> Task:
    return Task(title=title, status=status, required_capabilities=['reasoning'])


def recovery(title: str, status: TaskStatus, targets: list[str] | None = None) -> Task:
    return Task(
        title=title,
        status=status,
        result='recovery evidence' if status == TaskStatus.COMPLETE else None,
        metadata={
            'autonomy_recovery': True,
            'control_plane_atomic': True,
            'recovery_targets': list(targets or []),
        },
    )


def state_with(*tasks: Task) -> ProjectState:
    s = ProjectState(
        project_name='DEV189 qualification',
        goal='Execute real domain work without recovery churn',
        completion_criteria=['All planned deliverables are produced or explicitly marked out of scope.'],
        metadata={
            'require_goal_audit': True,
            'goal_audit_passed': False,
            'completion_confidence_threshold': 0.45,
        },
    )
    for t in tasks:
        s.tasks[t.id] = t
        s.root_task_ids.append(t.id)
    return s


def main() -> int:
    loop = AutonomousProjectLoop()
    completion = CompletionEngine()
    checks: dict[str, object] = {}

    # 1) A successful recovery must resolve BLOCKED targets, not only FAILED ones.
    blocked = domain('blocked-domain-work', TaskStatus.BLOCKED)
    r = recovery('successful-recovery', TaskStatus.COMPLETE, [blocked.id])
    s1 = state_with(blocked, r)
    applied = loop.apply_recovery_result(s1, r)
    checks['blocked_target_superseded_after_recovery'] = (
        applied.get('superseded') == 1 and blocked.status == TaskStatus.SUPERSEDED
    )

    # 2) Historical completed recovery evidence repairs a persisted blocked target.
    blocked2 = domain('persisted-blocked', TaskStatus.BLOCKED)
    r2 = recovery('persisted-complete-recovery', TaskStatus.COMPLETE, [blocked2.id])
    old_failed_control = recovery('old-failed-control-wrapper', TaskStatus.FAILED)
    s2 = state_with(blocked2, r2, old_failed_control)
    repaired = loop._repair_recovery_churn(s2)
    checks['persisted_churn_repair'] = (
        repaired.get('changed', 0) >= 2
        and blocked2.status == TaskStatus.SUPERSEDED
        and old_failed_control.status == TaskStatus.SUPERSEDED
    )

    # 3) Failed control-plane wrappers must not become project-completion blockers.
    domain_ready = domain('real-work', TaskStatus.BLOCKED)
    failed_control = recovery('control-failure-unique-id', TaskStatus.FAILED)
    s3 = state_with(domain_ready, failed_control)
    assessment = completion.assess(s3)
    blockers_text = '|'.join(assessment.blockers)
    checks['control_plane_excluded_from_completion'] = (
        failed_control.id not in blockers_text and domain_ready.id in blockers_text
    )

    # 4) Recovery signature must be stable even when control wrappers have different IDs.
    d4a = domain('same-domain', TaskStatus.BLOCKED)
    s4a = state_with(d4a, recovery('control-A', TaskStatus.FAILED))
    # Reuse the same domain id in a logically equivalent state.
    d4b = Task(id=d4a.id, title=d4a.title, status=TaskStatus.BLOCKED, required_capabilities=['reasoning'])
    s4b = state_with(d4b, recovery('control-B', TaskStatus.FAILED))
    a4a = completion.assess(s4a)
    a4b = completion.assess(s4b)
    b4a = loop._actionable_blockers(s4a, list(a4a.blockers))
    b4b = loop._actionable_blockers(s4b, list(a4b.blockers))
    checks['stable_recovery_signature_inputs'] = b4a == b4b == [f'{d4a.id}:blocked']

    # 5) At zero productive progress, completion-only blockers are deferred and no goal
    # audit may be created merely because control work is terminal.
    zero = domain('zero-progress-domain', TaskStatus.SUPERSEDED)
    s5 = state_with(zero, recovery('old-control', TaskStatus.SUPERSEDED))
    first = loop.ensure_progress(s5)
    checks['no_premature_goal_audit_at_zero_progress'] = first.get('status') != 'goal_audit_created'
    checks['zero_progress_actionable_blocker'] = 'goal_audit_required' not in '|'.join(
        loop._actionable_blockers(s5, list(completion.assess(s5).blockers))
    )

    # 6) Internal continuity NEEDS_REVIEW remains autonomous, not human attention.
    audit = Task(
        title='Goal continuity audit #1',
        status=TaskStatus.NEEDS_REVIEW,
        metadata={'goal_continuity_audit': True, 'control_plane_atomic': True},
    )
    s6 = state_with(audit)
    got = loop.ensure_progress(s6)
    checks['internal_needs_review_auto_recovers'] = (
        got.get('status') == 'goal_audit_review_auto_recovered' and audit.status == TaskStatus.RETRY
    )

    # 7) Final audit becomes eligible only after at least one productive success and
    # exhaustion of the productive batch.
    done = domain('productive-complete', TaskStatus.COMPLETE)
    done.result = 'real result'
    done.quality_score = 0.9
    s7 = state_with(done)
    got7 = loop.ensure_progress(s7)
    checks['audit_after_real_progress'] = got7.get('status') == 'goal_audit_created'

    # 8) Worst-case repeated recovery failures remain incident-bounded. Five ladder
    # stages are allowed; a sixth recovery task for the same blocker is forbidden.
    stuck = domain('endurance-blocked-domain', TaskStatus.BLOCKED)
    s8 = state_with(stuck)
    created_stages = []
    bounded = False
    for _ in range(80):
        row = loop.ensure_progress(s8)
        if row.get('status') == 'recovery_created':
            created_stages.append(row.get('recovery_stage'))
            s8.tasks[row['task_id']].status = TaskStatus.FAILED
        if row.get('status') == 'bounded_stall':
            bounded = True
            break
    checks['recovery_ladder_bounded'] = (
        bounded
        and created_stages == ['retry', 'fresh_worker', 'clean_audit', 'partial_replan', 'global_replan']
    )

    # 9) Reproduce the observed field scale: 204 historical recovery wrappers must
    # be retired in one migration pass without erasing the real blocked domain work.
    field_blocked = [domain(f'field-blocked-{i}', TaskStatus.BLOCKED) for i in range(3)]
    historical = [recovery(f'historical-recovery-{i}', TaskStatus.FAILED) for i in range(204)]
    s9 = state_with(*(field_blocked + historical))
    repair204 = loop._repair_recovery_churn(s9)
    checks['field_204_recoveries_repaired_once'] = (
        len(repair204.get('retired_control', [])) == 204
        and all(t.status == TaskStatus.SUPERSEDED for t in historical)
        and all(t.status == TaskStatus.BLOCKED for t in field_blocked)
    )

    ok = all(bool(v) for v in checks.values())
    result = {'ok': ok, 'checks': checks, 'count': len(checks)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
