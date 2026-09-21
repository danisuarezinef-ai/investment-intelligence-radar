from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.84-rc1-executable-route-integrity.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV309_BUILD_ROOT", "/tmp/ceo-dev309-closure-convergence"))
OLD_VERSION = "1.5.84-rc1-executable-route-integrity"
VERSION = "1.5.85-rc1-closure-convergence"
OLD_EPOCH = "dev308-executable-route-integrity-v1"
EPOCH = "dev309-closure-convergence-v1"


def replace_once(path: pathlib.Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_goal_engine() -> None:
    p = ROOT / "ceo_core" / "goal_engine.py"
    s = p.read_text(encoding="utf-8")
    if "import re\n" not in s:
        s = s.replace("import json\n", "import json\nimport re\n", 1)

    anchor = '''    def lock(
        self,
        objective: str,
'''
    new = '''    @staticmethod
    def infer_deliverables(objective: str) -> list[str]:
        """Extract explicit file deliverables from a free-text goal.

        This is intentionally conservative: only concrete filenames with common
        text/document extensions become locked deliverables. The original goal
        remains authoritative for everything else.
        """
        text = str(objective or "")
        pattern = r"(?<![A-Za-z0-9_])([A-Za-z0-9_.\\/\\-]+\\.(?:md|txt|json|csv|html))(?![A-Za-z0-9_])"
        out: list[str] = []
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            value = str(match).replace("\\\\", "/").strip().strip(".,;:()[]{}")
            if value and value not in out:
                out.append(value)
        return out

    def lock(
        self,
        objective: str,
'''
    if s.count(anchor) != 1:
        raise RuntimeError(f"goal engine method anchor={s.count(anchor)}")
    s = s.replace(anchor, new, 1)

    criteria_anchor = '''        criteria = [x.strip() for x in (completion_criteria or []) if x and x.strip()]
        if not criteria:
            criteria = list(DEFAULT_COMPLETION_CRITERIA)
        return GoalContract(
'''
    criteria_new = '''        criteria = [x.strip() for x in (completion_criteria or []) if x and x.strip()]
        if not criteria:
            criteria = list(DEFAULT_COMPLETION_CRITERIA)
        clean_deliverables = [x.strip() for x in (deliverables or []) if x and x.strip()]
        if not clean_deliverables:
            clean_deliverables = self.infer_deliverables(objective)
        return GoalContract(
'''
    if s.count(criteria_anchor) != 1:
        raise RuntimeError(f"goal deliverable inference anchor={s.count(criteria_anchor)}")
    s = s.replace(criteria_anchor, criteria_new, 1)
    old = '            deliverables=[x.strip() for x in (deliverables or []) if x and x.strip()],\n'
    if s.count(old) != 1:
        raise RuntimeError(f"goal deliverables line={s.count(old)}")
    s = s.replace(old, '            deliverables=clean_deliverables,\n', 1)
    p.write_text(s, encoding="utf-8")


def patch_result_protocol() -> None:
    p = ROOT / "ceo_core" / "result_protocol.py"
    s = p.read_text(encoding="utf-8")

    anchor = '''class WorkerDirective(BaseModel):
    """Machine-readable footer emitted by an AI worker turn."""
'''
    new = '''class FileWriteDirective(BaseModel):
    """Reversible workspace-local file write requested by an AI worker."""

    path: str = Field(min_length=1, max_length=240)
    content: str = ""


class WorkerDirective(BaseModel):
    """Machine-readable footer emitted by an AI worker turn."""
'''
    if s.count(anchor) != 1:
        raise RuntimeError(f"result protocol class anchor={s.count(anchor)}")
    s = s.replace(anchor, new, 1)

    old = '    evidence_refs: list[str] = Field(default_factory=list)\n'
    new2 = '''    evidence_refs: list[str] = Field(default_factory=list)
    write_files: list[FileWriteDirective] = Field(default_factory=list)
'''
    if s.count(old) != 1:
        raise RuntimeError(f"result protocol evidence anchor={s.count(old)}")
    p.write_text(s.replace(old, new2, 1), encoding="utf-8")


def patch_ai_worker() -> None:
    p = ROOT / "ceo_core" / "ai_worker.py"
    s = p.read_text(encoding="utf-8")

    rule_anchor = '                    "- Return work that another controller can evaluate and integrate.\\n"\n'
    rule_insert = (
        rule_anchor
        + '                    "- If a requested deliverable is a workspace file, use write_files with a RELATIVE path and complete content. "\n'
        + '                    "CEO will perform the guarded local write; never claim a file exists merely because you described it.\\n"\n'
        + '                    "- When auditing completion, use evidence_refs only from the explicit goal_audit_evidence_candidates supplied in context.\\n"\n'
    )
    if s.count(rule_anchor) != 1:
        raise RuntimeError(f"AI prompt operating-rule anchor={s.count(rule_anchor)}")
    s = s.replace(rule_anchor, rule_insert, 1)

    footer_anchor = '                    "\\"confidence\\":0.0,\\"requires_user\\":false}</CEO_RESULT>\\n"\n'
    footer_new = (
        '                    "\\"confidence\\":0.0,\\"requires_user\\":false,\\"evidence_refs\\":[],"\n'
        '                    "\\"write_files\\":[{\\"path\\":\\"relative/file.md\\",\\"content\\":\\"complete file content\\"}]}</CEO_RESULT>\\n"\n'
        '                    "- Use write_files=[] when no file should be written.\\n"\n'
    )
    if s.count(footer_anchor) != 1:
        raise RuntimeError(f"AI prompt footer schema anchor={s.count(footer_anchor)}")
    s = s.replace(footer_anchor, footer_new, 1)

    cont_anchor = (
        '                    "End the turn with one <CEO_RESULT>{...}</CEO_RESULT> control footer. "\n'
        '                    "If more work is needed in this chat, set status to continue/deepen/correct and provide next_instruction."\n'
    )
    cont_new = (
        '                    "End the turn with one <CEO_RESULT>{...}</CEO_RESULT> control footer using the full schema "\n'
        '                    "including evidence_refs and write_files. File writes must use relative workspace paths. "\n'
        '                    "If more work is needed in this chat, set status to continue/deepen/correct and provide next_instruction."\n'
    )
    if s.count(cont_anchor) != 1:
        raise RuntimeError(f"AI continuation footer anchor={s.count(cont_anchor)}")
    s = s.replace(cont_anchor, cont_new, 1)

    p.write_text(s, encoding="utf-8")

def patch_self_hosting_contract() -> None:
    p = ROOT / "ceo_core" / "self_hosting_runtime.py"
    s = p.read_text(encoding="utf-8")
    old = '                "control_footer": "<CEO_RESULT>{status,reason,next_instruction,followups,confidence,requires_user}</CEO_RESULT>",\n'
    new = '                "control_footer": "<CEO_RESULT>{status,reason,next_instruction,followups,confidence,requires_user,evidence_refs,write_files:[{path,content}]}</CEO_RESULT>",\n'
    if s.count(old) != 1:
        raise RuntimeError(f"self hosting contract footer={s.count(old)}")
    p.write_text(s.replace(old, new, 1), encoding="utf-8")


def patch_goal_completion_gate() -> None:
    p = ROOT / "ceo_core" / "goal_completion_gate.py"
    s = p.read_text(encoding="utf-8")

    anchor = '''    def evaluate(self, state: ProjectState, *, evidence_refs: list[str] | None = None) -> GoalAuditVerdict:
'''
    block = '''    def evidence_candidates(self, state: ProjectState, *, limit: int = 40) -> list[dict[str, Any]]:
        """Expose concrete existing evidence with stable task IDs to the auditor."""
        rows: list[dict[str, Any]] = []
        for task in state.leaf_tasks:
            if self._valid_ref_task(state, task.id) is None:
                continue
            md = task.metadata or {}
            row = {
                "task_id": task.id,
                "title": task.title,
                "status": task.status.value,
                "grounded": self._grounded(task),
                "artifacts": [str(x) for x in md.get("artifacts", [])][:8],
                "verified_artifacts": [str(x) for x in md.get("verified_artifacts", [])][:8],
                "independently_verified": bool(md.get("independently_verified") or md.get("verification_application")),
                "sources": [str(x) for x in (md.get("sources") or md.get("source_ids") or [])][:8],
                "result_excerpt": (task.result or "")[:500],
            }
            rows.append(row)
        rows.sort(
            key=lambda r: (
                bool(r["artifacts"] or r["verified_artifacts"]),
                bool(r["independently_verified"]),
                bool(r["grounded"]),
            ),
            reverse=True,
        )
        return rows[: max(1, int(limit))]

    def auto_evidence_refs(self, state: ProjectState) -> list[str]:
        """Deterministically select real evidence; never manufacture task IDs."""
        candidates = self.evidence_candidates(state, limit=100)
        wanted = max(1, int(state.metadata.get("min_goal_audit_evidence_refs", 1)))
        selected: list[str] = []

        def add(row: dict[str, Any]) -> None:
            tid = str(row.get("task_id") or "")
            if tid and tid not in selected:
                selected.append(tid)

        for row in candidates:
            if row.get("artifacts") or row.get("verified_artifacts"):
                add(row)
                break
        for row in candidates:
            if row.get("independently_verified"):
                add(row)
                break
        for row in candidates:
            if row.get("grounded"):
                add(row)
            if len(selected) >= wanted:
                break
        for row in candidates:
            add(row)
            if len(selected) >= wanted:
                break
        return selected

    def evaluate(self, state: ProjectState, *, evidence_refs: list[str] | None = None) -> GoalAuditVerdict:
'''
    if s.count(anchor) != 1:
        raise RuntimeError(f"goal gate evaluate anchor={s.count(anchor)}")
    p.write_text(s.replace(anchor, block, 1), encoding="utf-8")


def patch_scheduler() -> None:
    p = ROOT / "ceo_core" / "scheduler.py"
    s = p.read_text(encoding="utf-8")

    header = s[:1200]
    if "import pathlib\n" not in header or "import re\n" not in header:
        anchor = "import asyncio\n"
        if s.count(anchor) != 1:
            raise RuntimeError(f"scheduler import anchor={s.count(anchor)}")
        additions = "import asyncio\n"
        if "import pathlib\n" not in header:
            additions += "import pathlib\n"
        if "import re\n" not in header:
            additions += "import re\n"
        s = s.replace(anchor, additions, 1)

    old_import = "from .self_hosting_tools import ArtifactExchangeLayer, ProviderContextRecovery, WorkerSessionManager\n"
    new_import = "from .self_hosting_tools import ArtifactExchangeLayer, FilesystemOperations, ProviderContextRecovery, WorkerSessionManager\n"
    if s.count(old_import) != 1:
        raise RuntimeError(f"scheduler self-hosting import={s.count(old_import)}")
    s = s.replace(old_import, new_import, 1)

    s = s.replace(f'RELIABILITY_EPOCH = "{OLD_EPOCH}"', f'RELIABILITY_EPOCH = "{EPOCH}"', 1)
    if f'RELIABILITY_EPOCH = "{EPOCH}"' not in s:
        raise RuntimeError("scheduler epoch replacement failed")

    migration_anchor = '''    state.metadata.pop("control_plane_circuit_open", None)
    state.metadata.pop("productive_stall_escape_required", None)

    # DEV308: rebase the separate recovery-churn fuse and remove only stale
'''
    migration_new = '''    state.metadata.pop("control_plane_circuit_open", None)
    state.metadata.pop("productive_stall_escape_required", None)

    # DEV309 closure contract migration. Explicit filenames in a free-text goal are
    # real deliverables, and a bounded single-artifact objective must not inherit the
    # same evidence/generation thresholds as a long research or implementation project.
    if not state.goal_deliverables:
        matches = re.findall(
            r"(?<![A-Za-z0-9_])([A-Za-z0-9_.\\/\\-]+\\.(?:md|txt|json|csv|html))(?![A-Za-z0-9_])",
            str(state.goal or ""),
            flags=re.IGNORECASE,
        )
        state.goal_deliverables = list(dict.fromkeys(
            str(x).replace("\\\\", "/").strip().strip(".,;:()[]{}") for x in matches if str(x).strip()
        ))

    single_artifact = len(state.goal_deliverables) == 1
    closure_profile = "bounded_single_artifact" if single_artifact else "general"
    if single_artifact:
        state.metadata["min_goal_audit_evidence_refs"] = 2
        state.metadata["min_goal_audit_grounded_refs"] = 2
        state.metadata["min_goal_continuity_generations"] = 1
        state.metadata["max_goal_continuity_generations"] = 4
    else:
        state.metadata.setdefault("min_goal_audit_evidence_refs", 3)
        state.metadata.setdefault("min_goal_audit_grounded_refs", 2)
        state.metadata.setdefault("min_goal_continuity_generations", 3)
        state.metadata.setdefault("max_goal_continuity_generations", 24)
    state.metadata["closure_profile_v1"] = {
        "epoch": RELIABILITY_EPOCH,
        "profile": closure_profile,
        "deliverables": list(state.goal_deliverables),
        "max_generations": int(state.metadata.get("max_goal_continuity_generations", 24)),
    }

    # Field repair for the observed #173 loop. Preserve history but start one fresh,
    # bounded closure epoch and retire only active continuity machinery.
    historical_generation = int(state.metadata.get("goal_continuity_generation", 0) or 0)
    max_generation = int(state.metadata.get("max_goal_continuity_generations", 24) or 24)
    if historical_generation > max_generation:
        retired_closure = []
        for task in state.leaf_tasks:
            if protected_human_gate(task):
                continue
            if not (
                is_goal_audit_lineage(state, task)
                or task.metadata.get("continuity_gap_recovery")
            ):
                continue
            if task.status in {
                TaskStatus.WAITING, TaskStatus.READY, TaskStatus.RUNNING,
                TaskStatus.BLOCKED, TaskStatus.RETRY, TaskStatus.NEEDS_REVIEW,
            }:
                task.status = TaskStatus.SUPERSEDED
                task.worker_id = None
                task.metadata["superseded_reason"] = "dev309_restart_bounded_closure_epoch"
                retired_closure.append(task.id)
        state.metadata["historical_goal_continuity_generation"] = historical_generation
        state.metadata["goal_continuity_generation"] = 0
        state.metadata["continuity_nonspawn_rejections"] = 0
        state.metadata["goal_audit_passed"] = False
        state.metadata.pop("last_goal_audit_rejection", None)
        state.metadata["dev309_closure_epoch_restarted"] = {
            "historical_generation": historical_generation,
            "retired_active_closure_tasks": retired_closure,
            "profile": closure_profile,
            "ts": now,
        }

    # DEV308: rebase the separate recovery-churn fuse and remove only stale
'''
    if s.count(migration_anchor) != 1:
        raise RuntimeError(f"scheduler closure migration anchor={s.count(migration_anchor)}")
    s = s.replace(migration_anchor, migration_new, 1)

    context_anchor = '''            request_context = {
                "human_interventions_avoided": self.state.human_interventions_avoided,
                **self.context_builder.build(self.state, task),
            }
'''
    context_new = '''            request_context = {
                "human_interventions_avoided": self.state.human_interventions_avoided,
                **self.context_builder.build(self.state, task),
            }
            if task.metadata.get("goal_continuity_audit"):
                request_context["goal_audit_evidence_candidates"] = self.goal_completion_gate.evidence_candidates(
                    self.state, limit=40
                )
                request_context["goal_audit_requirements"] = {
                    "min_evidence_refs": int(self.state.metadata.get("min_goal_audit_evidence_refs", 1)),
                    "min_grounded_refs": int(self.state.metadata.get("min_goal_audit_grounded_refs", 0)),
                    "generation": int(self.state.metadata.get("goal_continuity_generation", 0)),
                    "required_generation": int(self.state.metadata.get("min_goal_continuity_generations", 1)),
                    "deliverables": list(self.state.goal_deliverables),
                }
'''
    if s.count(context_anchor) != 1:
        raise RuntimeError(f"scheduler audit context anchor={s.count(context_anchor)}")
    s = s.replace(context_anchor, context_new, 1)

    result_anchor = '''            if result.success and not str(result.text or "").strip() and not list(result.artifacts or []):
'''
    result_block = '''            directive = extract_directive(result.text)
            if result.success and directive and getattr(directive, "write_files", None):
                if not workspace_root:
                    result.success = False
                    result.error = "Worker requested workspace file writes but no workspace root is configured."
                else:
                    try:
                        fs = FilesystemOperations(workspace_root)
                        exchange = ArtifactExchangeLayer(workspace_root)
                        written = []
                        for spec in list(directive.write_files)[:20]:
                            relative = str(spec.path).strip()
                            if not relative:
                                continue
                            row = fs.write_text(relative, str(spec.content))
                            verified = exchange.register(
                                self.state, relative, task_id=task.id, direction="worker_output"
                            )
                            evidence = self.deliverable_evidence_v1.record_file(
                                self.state, task, pathlib.Path(workspace_root) / relative, root=workspace_root
                            )
                            if relative not in result.artifacts:
                                result.artifacts.append(relative)
                            written.append({
                                "path": relative,
                                "sha256": row.get("sha256"),
                                "size_bytes": row.get("size_bytes"),
                                "artifact_id": verified.get("artifact_id"),
                                "evidence_ref": evidence.ref,
                            })
                        if written:
                            task.metadata.setdefault("verified_artifacts", []).extend(
                                x["artifact_id"] for x in written if x.get("artifact_id")
                            )
                            task.metadata["workspace_writes_v1"] = written
                            self._activity_event(
                                "workspace_artifact_written", task, provider=provider_name,
                                detail=f"Materializados y verificados {len(written)} archivo(s) en el workspace",
                            )
                    except Exception as exc:
                        result.success = False
                        result.error = f"Workspace artifact write failed: {type(exc).__name__}: {exc}"

            if result.success and not str(result.text or "").strip() and not list(result.artifacts or []):
'''
    if s.count(result_anchor) != 1:
        raise RuntimeError(f"scheduler result materialization anchor={s.count(result_anchor)}")
    s = s.replace(result_anchor, result_block, 1)

    decide_anchor = '''            spawned = self.controller.apply(self.state, task, result, decision)
            if task.metadata.get("goal_continuity_audit") and spawned:
'''
    decide_new = '''            spawned = self.controller.apply(self.state, task, result, decision)
            if (
                task.status == TaskStatus.COMPLETE
                and (
                    "verification" in set(task.required_capabilities or [])
                    or str(task.metadata.get("task_role") or "") == "verification"
                )
                and (task.result or "").strip()
            ):
                task.metadata["independently_verified"] = True
                task.metadata["verification_application"] = {
                    "verified_at": utcnow().isoformat(),
                    "provider": provider_name,
                    "task_id": task.id,
                }
            if task.metadata.get("goal_continuity_audit") and spawned:
'''
    if s.count(decide_anchor) != 1:
        raise RuntimeError(f"scheduler verification marker anchor={s.count(decide_anchor)}")
    s = s.replace(decide_anchor, decide_new, 1)

    old_directive = '''                directive = extract_directive(result.text)
                evidence_refs = list(getattr(directive, "evidence_refs", []) or []) if directive else []
                verdict = self.goal_completion_gate.evaluate(self.state, evidence_refs=evidence_refs)
'''
    new_directive = '''                directive = directive or extract_directive(result.text)
                claimed_refs = list(getattr(directive, "evidence_refs", []) or []) if directive else []
                auto_refs = self.goal_completion_gate.auto_evidence_refs(self.state)
                evidence_refs = list(dict.fromkeys([str(x) for x in claimed_refs + auto_refs if str(x).strip()]))
                verdict = self.goal_completion_gate.evaluate(self.state, evidence_refs=evidence_refs)
'''
    if s.count(old_directive) != 1:
        raise RuntimeError(f"scheduler audit evidence anchor={s.count(old_directive)}")
    s = s.replace(old_directive, new_directive, 1)

    gap_anchor = '''        specs = [
            (
                "Continuity recovery: map the highest-impact unresolved requirement to one concrete next action" + tag,
'''
    gap_new = '''        missing_deliverables = [
            str(g).split(":", 1)[1]
            for g in gaps
            if str(g).startswith("deliverable_unproven:") and ":" in str(g)
        ]
        if missing_deliverables:
            target = missing_deliverables[0].strip()
            specs = [
                (
                    f"Closure repair: create missing deliverable {target}" + tag,
                    (
                        f"Create the missing deliverable {target} in the CEO workspace. "
                        "Your substantive response must be the complete intended file content and your CEO_RESULT must use "
                        f"write_files=[{{\"path\":\"{target}\",\"content\":\"...complete content...\"}}]. "
                        "Do not merely describe the file. Use the locked project goal to include every requested field."
                    ),
                    ["reasoning"], "general",
                ),
                (
                    f"Closure repair: independently verify deliverable {target}" + tag,
                    (
                        f"Independently verify that {target} exists in the workspace, is non-empty, and satisfies the locked goal. "
                        "Report concrete verification findings; do not fabricate filesystem evidence."
                    ),
                    ["reasoning", "verification"], "code_review",
                ),
            ]
        else:
            specs = [
            (
                "Continuity recovery: map the highest-impact unresolved requirement to one concrete next action" + tag,
'''
    if s.count(gap_anchor) != 1:
        raise RuntimeError(f"scheduler gap specs anchor={s.count(gap_anchor)}")
    s = s.replace(gap_anchor, gap_new, 1)

    # Close the newly introduced else: specs list immediately after the original three tuples.
    close_anchor = '''            (
                "Continuity recovery: independently verify the new result against the locked goal" + tag,
                "Verify the preceding result against the locked goal and acceptance criteria. Record what was actually verified, what remains unresolved, and concrete evidence references where available.",
                ["reasoning", "verification"], "code_review",
            ),
        ]
        spawned: list[Task] = []
'''
    close_new = '''            (
                "Continuity recovery: independently verify the new result against the locked goal" + tag,
                "Verify the preceding result against the locked goal and acceptance criteria. Record what was actually verified, what remains unresolved, and concrete evidence references where available.",
                ["reasoning", "verification"], "code_review",
            ),
            ]
        spawned: list[Task] = []
'''
    if s.count(close_anchor) != 1:
        raise RuntimeError(f"scheduler gap close anchor={s.count(close_anchor)}")
    s = s.replace(close_anchor, close_new, 1)

    p.write_text(s, encoding="utf-8")


def patch_autonomous_loop() -> None:
    p = ROOT / "ceo_core" / "autonomous_loop.py"
    s = p.read_text(encoding="utf-8")

    anchor = '''                if not existing_audits:
                    generation = int(state.metadata.get("goal_continuity_generation", 0)) + 1
                    audit = Task(
'''
    new = '''                if not existing_audits:
                    generation = int(state.metadata.get("goal_continuity_generation", 0)) + 1
                    max_generation = int(state.metadata.get("max_goal_continuity_generations", 24) or 24)
                    if generation > max_generation:
                        last = dict(state.metadata.get("last_goal_audit_rejection") or {})
                        state.metadata["autonomy_stalled"] = {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "action": "closure_convergence_exhausted",
                            "generation": generation - 1,
                            "max_generation": max_generation,
                            "gaps": list(last.get("gaps") or [])[:20],
                        }
                        state.metadata["operator_productivity_state"] = "BLOQUEADO"
                        state.metadata["operator_block_reason"] = (
                            f"Cierre acotado agotado tras {max_generation} auditorías; "
                            "CEO no repetirá el bucle indefinidamente."
                        )
                        return {
                            "status": "closure_bounded_stall",
                            "created": 0,
                            "changed": 0,
                            "generation": generation - 1,
                            "max_generation": max_generation,
                            "gaps": list(last.get("gaps") or [])[:20],
                        }
                    audit = Task(
'''
    if s.count(anchor) != 1:
        raise RuntimeError(f"autonomous loop generation cap anchor={s.count(anchor)}")
    p.write_text(s.replace(anchor, new, 1), encoding="utf-8")


def patch_import_pathlib() -> None:
    # Imports are inserted deterministically at module header by patch_scheduler.
    p = ROOT / "ceo_core" / "scheduler.py"
    s = p.read_text(encoding="utf-8")
    header = s[:1200]
    if "import pathlib\n" not in header or "import re\n" not in header:
        raise RuntimeError("DEV309 scheduler module imports missing from header")

def update_version_and_contract() -> None:
    for rel in ("scripts/ceo_stdlib_work_mode.py", "scripts/install_windows_bootstrap.py"):
        p = ROOT / rel
        if p.is_file():
            p.write_text(p.read_text(encoding="utf-8").replace(OLD_VERSION, VERSION), encoding="utf-8")

    cpath = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(cpath.read_text(encoding="utf-8"))
    contract["app_version"] = VERSION
    hashes = dict(contract.get("file_hashes") or {})
    for rel in hashes:
        fp = ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract path {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    cpath.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if not BASE.is_file():
        raise RuntimeError(f"missing base {BASE}")
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    patch_goal_engine()
    patch_result_protocol()
    patch_ai_worker()
    patch_self_hosting_contract()
    patch_goal_completion_gate()
    patch_scheduler()
    patch_import_pathlib()
    patch_autonomous_loop()
    update_version_and_contract()

    print(json.dumps({
        "ok": True,
        "root": str(ROOT),
        "base": OLD_VERSION,
        "version": VERSION,
        "epoch": EPOCH,
        "fixes": [
            "explicit_file_deliverable_inference",
            "guarded_workspace_write_protocol",
            "artifact_registration_and_hash_evidence",
            "audit_evidence_candidates_with_real_task_ids",
            "deterministic_auto_evidence_refs",
            "bounded_single_artifact_completion_profile",
            "goal_continuity_generation_cap",
            "field_migration_from_173_audit_loop",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
