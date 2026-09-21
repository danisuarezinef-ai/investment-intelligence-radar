from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
import logging.handlers
import os
import secrets
import sys
import subprocess
import threading
import time
import urllib.request
import webbrowser

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ceo_core.decomposer import TaskDecomposer
from ceo_core.goal_engine import GoalEngine
from ceo_core.graph import TaskGraph
from ceo_core.llm_planner import LLMTaskPlanner
from ceo_core.models import DecisionStatus, TaskStatus
from ceo_core.planning import BaselineTaskPlanner
from ceo_core.provider_factory import build_providers
from ceo_core.provider_secrets import provider_secret_status, save_provider_secret, delete_provider_secret
from ceo_core.project_catalog import ProjectCatalog
from ceo_core.routing import MultiProviderRouter
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.store import JsonCheckpointStore
from ceo_core.sqlite_store import SqliteCheckpointStore
from ceo_core.absence import AbsenceMode
from ceo_core.control import GoalRevisionManager, SelectivePause
from ceo_core.exporter import ProjectExporter
from ceo_core.final_report import FinalReportBuilder
from ceo_core.templates import apply_template
from ceo_core.control_center import ProjectControlCenter
from ceo_core.project_map import ProjectMapBuilder
from ceo_core.resource_adaptive import CapacityProfiler
from ceo_core.recovery import RecoveryManager
from ceo_core.runtime import bundle_root, user_data_root, configure_playwright_runtime
from ceo_core.validation import ValidationRegistry, StrictReleaseGates
from ceo_core.update_manager import UpdateManager
from ceo_core.continuity import ContinuityManager
from ceo_core.operator_controls import OperatorControls
from ceo_core.production_intelligence import ProductionIntelligenceCore
from ceo_core.long_horizon import SemanticProjectMemory
from ceo_core.security_governance_v2 import SecurityGovernanceV2
from ceo_core.operational_scale import OperatingModeEngine, AutonomyConfidenceEngine
from ceo_core.release_engineering import ProjectWorkspaceManager
from ceo_core.learning_governance import ConfidenceCalibrationEngine
from ceo_core.quality_engineering import QualityEngineeringCore
from ceo_core.scale_security import ScaleSecurityCore
from ceo_core.release_candidate_v1 import ReleaseCandidateCore
from ceo_core.desktop_integration import DesktopBrowserIntegrationCore
from ceo_core.self_hosting_runtime import SelfHostingRuntimeCore, DesktopMode
from ceo_core.self_hosting_tools import SelfHostingWorkspace
from ceo_core.self_hosting_beta import SupervisedStep
from ceo_core.operational_autonomy import OperationalAutonomyCore
from ceo_core.real_work_queue import RealWorkQueue


ROOT = bundle_root()
DATA_DIR = user_data_root()
configure_playwright_runtime()
STATIC_DIR = ROOT / "ceo_app" / "static"
LEGACY_STORE = JsonCheckpointStore(DATA_DIR / "project_state.json")
STORE: SqliteCheckpointStore = SqliteCheckpointStore(DATA_DIR / "ceo.db")
PROJECTS = ProjectCatalog(DATA_DIR / "projects")
DECOMPOSER = TaskDecomposer()
BASELINE_PLANNER = BaselineTaskPlanner(DECOMPOSER)
GRAPH = TaskGraph()
GOAL_ENGINE = GoalEngine()
providers = build_providers(ROOT, DATA_DIR)
router = MultiProviderRouter(providers)
# If the first real provider is an AIWorkerProvider its transport can plan too; otherwise deterministic fallback.
first_transport = getattr(providers[0], "transport", None)
PLANNER = LLMTaskPlanner(first_transport, fallback=BASELINE_PLANNER) if first_transport else BASELINE_PLANNER
scheduler: ContinuousScheduler | None = None
_catalog_touch_ts = 0.0

def _rebuild_provider_stack() -> None:
    global providers, router, PLANNER
    providers = build_providers(ROOT, DATA_DIR)
    router = MultiProviderRouter(providers)
    first = getattr(providers[0], "transport", None) if providers else None
    PLANNER = LLMTaskPlanner(first, fallback=BASELINE_PLANNER) if first else BASELINE_PLANNER
    if scheduler is not None:
        scheduler.router = router
CONTROL_CENTER = ProjectControlCenter()
PROJECT_MAP = ProjectMapBuilder()
CAPACITY = CapacityProfiler()
RECOVERY = RecoveryManager()
VALIDATION = ValidationRegistry(DATA_DIR / "validation_registry.json")
VALIDATION_GATES = StrictReleaseGates()
UPDATE_MANAGER = UpdateManager()
CONTINUITY = ContinuityManager()
OPERATOR_CONTROLS = OperatorControls()
PRODUCTION_CORE = ProductionIntelligenceCore()
SEMANTIC_MEMORY = SemanticProjectMemory()
SECURITY_V2 = SecurityGovernanceV2()
OPERATING_MODES = OperatingModeEngine()
AUTONOMY_CONFIDENCE = AutonomyConfidenceEngine()
CONFIDENCE_CALIBRATION = ConfidenceCalibrationEngine()
QUALITY_ENGINEERING = QualityEngineeringCore()
SCALE_SECURITY = ScaleSecurityCore()
RELEASE_CANDIDATE = ReleaseCandidateCore()
DESKTOP_BROWSER = DesktopBrowserIntegrationCore()
SELF_HOSTING = SelfHostingRuntimeCore(str(ROOT))
OPERATIONAL_AUTONOMY = OperationalAutonomyCore(ROOT, data_root=DATA_DIR)
REAL_WORK_QUEUE = RealWorkQueue()


class StartRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    goal: str = Field(min_length=3, max_length=5000)
    definition: str | None = Field(default=None, max_length=10000)
    success_definition: str | None = Field(default=None, max_length=10000)
    constraints: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    deadline: str | None = None
    urgency: int = Field(default=50, ge=1, le=100)
    budget_limit: float | None = Field(default=None, ge=0)
    priority_mode: str = "balanced"
    power_percent: int = Field(default=30, ge=1, le=100)
    template: str = "general"


class PowerRequest(BaseModel):
    power_percent: int = Field(ge=1, le=100)


class ToggleRequest(BaseModel):
    enabled: bool


class DesktopModeRequest(BaseModel):
    mode: str = Field(pattern="^(read_only|supervised|autonomous)$")


class OperatorDeviceRouteRequest(BaseModel):
    task_kind: str = Field(min_length=1, max_length=120)
    estimated_ram_gb: float = Field(default=0.0, ge=0.0, le=256.0)
    requires_windows_ui: bool = False
    mobile_available: bool = True
    mobile_ram_gb: float = Field(default=24.0, ge=0.0, le=256.0)


class OperatorFrictionPlanRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class SelfHostingWorkspaceRequest(BaseModel):
    label: str = Field(default="self-hosting", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")


class SelfImprovementMissionRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=2000)
    target_area: str = Field(min_length=1, max_length=300)
    hypothesis: str = Field(default="", max_length=4000)
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)


class SelfHostingCandidateBuildRequest(BaseModel):
    mission_id: str = Field(min_length=3, max_length=100)
    candidate_root: str = Field(min_length=1, max_length=2000)
    version: str = Field(min_length=1, max_length=120)


class SelfHostingReleaseDiffRequest(BaseModel):
    mission_id: str = Field(min_length=3, max_length=100)
    candidate_root: str = Field(min_length=1, max_length=2000)


class SelfHostingPromotionDecisionRequest(BaseModel):
    mission_id: str = Field(min_length=3, max_length=100)
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    human_confirmed: bool = False
    approval_token: str = Field(default="", max_length=1000)
    note: str = Field(default="", max_length=2000)





class SelfHostingSupervisedSessionRequest(BaseModel):
    label: str = Field(default="daily-supervised", min_length=1, max_length=200)
    field_executed: bool = False
    platform: str = Field(default="unknown", max_length=80)
    evidence: list[str] = Field(default_factory=list)


class SelfHostingSupervisedStepRequest(BaseModel):
    action: str = Field(min_length=1, max_length=500)
    success: bool
    autonomous: bool
    human_intervention: bool = False
    approval_required: bool = False
    recovery_attempted: bool = False
    recovery_success: bool | None = None
    friction: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=0.0, ge=0)
    task_id: str | None = Field(default=None, max_length=200)
    details: dict = Field(default_factory=dict)


class SelfHostingPermissionApplyRequest(BaseModel):
    target: str = Field(pattern="^(supervised|autonomous)$")
    human_confirmed: bool = False
    approval_token: str = Field(default="", max_length=1000)




class EmergencyStopRequest(BaseModel):
    reason: str = Field(default="human emergency stop", min_length=1, max_length=1000)


class SafeResumeRequest(BaseModel):
    human_confirmed: bool = False
    pending_actions: list[dict] = Field(default_factory=list)


class ProviderCredentialRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=1000)


class ResourcePresetRequest(BaseModel):
    preset: str


class AutonomyProfileRequest(BaseModel):
    level: str


class OperatingModeRequest(BaseModel):
    mode: str


class ProjectDuplicateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)


class ProjectNameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class ProjectDeleteRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=200)


class DecisionRequest(BaseModel):
    selected: str


class WorkSettingsRequest(BaseModel):
    verification_percent: int | None = Field(default=None, ge=0, le=100)
    depth_percent: int | None = Field(default=None, ge=0, le=100)
    exploration_percent: int | None = Field(default=None, ge=0, le=100)
    budget_limit: float | None = Field(default=None, ge=0)
    priority_mode: str | None = None


class GoalRevisionRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=5000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler, STORE
    restored = None
    # One canonical project root. Re-index orphan canonical stores and import the
    # historical single DB once; neither operation deletes user data.
    PROJECTS.reconcile_storage()
    PROJECTS.migrate_legacy_store(DATA_DIR / "ceo.db")
    PROJECTS.migrate_projects()
    active_id = PROJECTS.active_project_id()
    if active_id:
        try:
            STORE = PROJECTS.store(active_id)
            restored = STORE.load()
        except Exception:
            restored = None
    if restored is None and not PROJECTS.list(include_archived=True):
        restored = SqliteCheckpointStore(DATA_DIR / "ceo.db").load() or LEGACY_STORE.load()
        if restored:
            STORE = PROJECTS.store(restored.id)
            STORE.save(restored)
            PROJECTS.register(restored, make_active=True)
    if restored and restored.goal:
        OPERATIONAL_AUTONOMY.initialize(restored)
        REAL_WORK_QUEUE.initialize(restored)
        if restored.completed_at is None:
            restored = STORE.prepare_for_resume(restored)
            RECOVERY.prepare(restored)
        scheduler = ContinuousScheduler(restored, None, STORE, graph=GRAPH, router=router)
        if restored.completed_at is None and not restored.paused:
            scheduler.start()
    yield
    if scheduler:
        # Graceful shutdown closes the autonomous loop before the final durable
        # checkpoint. This avoids losing the last transition during Windows exit/restart.
        if scheduler._runner and not scheduler._runner.done():
            await scheduler.stop()
        CONTINUITY.capture(scheduler.state, reason="app_shutdown")
        STORE.save(scheduler.state)
        PROJECTS.touch(scheduler.state)


app = FastAPI(title="CEO de IAs", version="1.1.0-dev13-real-work-queue", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/start")
async def start_project(request: StartRequest):
    global scheduler, STORE
    if scheduler and scheduler._runner and not scheduler._runner.done():
        await scheduler.stop()
        STORE.save(scheduler.state); PROJECTS.touch(scheduler.state)
    goal = GOAL_ENGINE.lock(
        request.goal, definition=request.definition, success_definition=request.success_definition,
        constraints=request.constraints, completion_criteria=request.completion_criteria,
        deliverables=request.deliverables, forbidden_actions=request.forbidden_actions,
        deadline=request.deadline, urgency=request.urgency, budget_limit=request.budget_limit,
    )
    state = await PLANNER.plan(goal)
    GOAL_ENGINE.apply(state, goal)
    state.project_name = (request.name or request.goal[:80]).strip()
    state.power_percent = request.power_percent
    state.priority_mode = request.priority_mode
    state.metadata.setdefault("autonomy_level", "balanced")
    state.metadata.setdefault("resource_preset", "custom")
    apply_template(state, request.template)
    SECURITY_V2.initialize(state)
    OPERATING_MODES.set(state, "normal")
    PRODUCTION_CORE.initialize_project(state)
    QUALITY_ENGINEERING.initialize_project(state)
    SEMANTIC_MEMORY.ingest_project(state)
    # User constraints and forbidden actions are binding project invariants.
    for idx, constraint in enumerate(state.goal_constraints):
        SCALE_SECURITY.bindings.bind(state, key=f"goal_constraint:{idx}", value=constraint, rationale="user goal constraint", authority="user", source_ref="goal_contract")
    for idx, action in enumerate(state.metadata.get("forbidden_actions", [])):
        SCALE_SECURITY.bindings.bind(state, key=f"forbidden_action:{idx}", value=action, rationale="user forbidden action", authority="user", source_ref="goal_contract")
    SCALE_SECURITY.snapshot(state)
    DESKTOP_BROWSER.initialize(state)
    SELF_HOSTING.initialize(state)
    OPERATIONAL_AUTONOMY.initialize(state)
    REAL_WORK_QUEUE.initialize(state)
    state.metadata.setdefault("real_work_intake_v1", {
        "mode": "general_supervised",
        "automatic_spending": False,
        "automatic_candidate_promotion": False,
        "created_via": "goal_engine",
    })
    ProjectWorkspaceManager(PROJECTS.store_path(state.id).parent).create(state)
    STORE = PROJECTS.store(state.id)
    STORE.save(state); PROJECTS.register(state, make_active=True)
    scheduler = ContinuousScheduler(state, None, STORE, graph=GRAPH, router=router)
    scheduler.start()
    return snapshot()


@app.get("/api/work-queue")
async def get_work_queue(limit: int = 100):
    if not scheduler:
        return {"active": False, "queue": [], "counts": {}, "safety": {"automatic_spending": False, "automatic_candidate_promotion": False, "destructive_actions_require_gate": True}}
    return {"active": True, **REAL_WORK_QUEUE.snapshot(scheduler.state, limit=max(1, min(500, int(limit))))}


@app.get("/api/state")
async def get_state():
    return snapshot()


@app.get("/api/providers")
async def provider_state():
    health = [await provider.healthcheck() for provider in providers]
    return [h.model_dump() for h in health]


@app.get("/api/provider-credentials")
async def provider_credentials():
    return [asdict(row) for row in provider_secret_status()]


@app.post("/api/provider-credentials/{provider}")
async def set_provider_credential(provider: str, request: ProviderCredentialRequest):
    try:
        status = save_provider_secret(provider, request.api_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    _rebuild_provider_stack()
    return asdict(status)


@app.delete("/api/provider-credentials/{provider}")
async def remove_provider_credential(provider: str):
    try:
        delete_provider_secret(provider)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    _rebuild_provider_stack()
    return {"provider": provider, "configured": False}


@app.get("/api/projects")
async def list_projects(include_archived: bool = False):
    if scheduler:
        PROJECTS.touch(scheduler.state)
    return PROJECTS.list(include_archived=include_archived)


@app.get("/api/projects/cleanup-candidates")
async def project_cleanup_candidates():
    return {"automatic_action": False, "candidates": PROJECTS.cleanup_candidates()}


@app.post("/api/projects/{project_id}/pause")
async def pause_project_by_id(project_id: str):
    if scheduler and scheduler.state.id == project_id:
        scheduler.state.paused = True
        CONTINUITY.capture(scheduler.state, reason="project_pause")
        STORE.save(scheduler.state); PROJECTS.touch(scheduler.state)
        return {"project": PROJECTS.list(include_archived=True), "state": snapshot()}
    try:
        state = PROJECTS.set_paused(project_id, True)
    except KeyError as exc:
        raise HTTPException(404, "Project not found") from exc
    return {"project_id": project_id, "paused": state.paused}


@app.post("/api/projects/{project_id}/resume")
async def resume_project_by_id(project_id: str):
    global scheduler, STORE
    if scheduler and scheduler.state.id != project_id and scheduler._runner and not scheduler._runner.done():
        await scheduler.stop(); STORE.save(scheduler.state); PROJECTS.touch(scheduler.state)
    try:
        new_store = PROJECTS.store(project_id); state = new_store.load()
    except Exception as exc:
        raise HTTPException(404, f"Project could not be loaded: {exc}") from exc
    if state is None:
        raise HTTPException(404, "Project not found")
    STORE = new_store; PROJECTS.set_active(project_id)
    state = STORE.prepare_for_resume(state); RECOVERY.prepare(state); state.paused = False
    CONTINUITY.mark_resume(state, source="project_resume")
    STORE.save(state); PROJECTS.touch(state)
    scheduler = ContinuousScheduler(state, None, STORE, graph=GRAPH, router=router); scheduler.start()
    return snapshot()


@app.post("/api/projects/{project_id}/duplicate")
async def duplicate_project(project_id: str, request: ProjectDuplicateRequest):
    try:
        clone = PROJECTS.duplicate(project_id, name=request.name, make_active=False)
    except KeyError as exc:
        raise HTTPException(404, "Project not found") from exc
    return {"project_id": clone.id, "name": clone.project_name, "paused": clone.paused}


@app.post("/api/projects/{project_id}/rename")
async def rename_project(project_id: str, request: ProjectNameRequest):
    try:
        store = PROJECTS.store(project_id); state = store.load()
    except Exception as exc:
        raise HTTPException(404, "Project not found") from exc
    if state is None: raise HTTPException(404, "Project not found")
    state.project_name = request.name.strip(); store.save(state); PROJECTS.touch(state)
    if scheduler and scheduler.state.id == project_id: scheduler.state.project_name = state.project_name
    return {"project_id": project_id, "name": state.project_name}


@app.post("/api/projects/{project_id}/unarchive")
async def unarchive_project(project_id: str):
    try: PROJECTS.archive(project_id, False)
    except KeyError as exc: raise HTTPException(404, "Project not found") from exc
    return {"archived": False, "project_id": project_id}


@app.post("/api/projects/{project_id}/activate")
async def activate_project(project_id: str):
    global scheduler, STORE
    if scheduler and scheduler._runner and not scheduler._runner.done():
        await scheduler.stop()
        STORE.save(scheduler.state); PROJECTS.touch(scheduler.state)
    try:
        new_store = PROJECTS.store(project_id)
        state = new_store.load()
    except Exception as exc:
        raise HTTPException(404, f"Project could not be loaded: {exc}") from exc
    if state is None:
        raise HTTPException(404, "Project not found")
    STORE = new_store; PROJECTS.set_active(project_id)
    if state.completed_at is None:
        state = STORE.prepare_for_resume(state); RECOVERY.prepare(state)
    scheduler = ContinuousScheduler(state, None, STORE, graph=GRAPH, router=router)
    if state.completed_at is None and not state.paused:
        scheduler.start()
    return snapshot()


@app.post("/api/projects/{project_id}/archive")
async def archive_project(project_id: str):
    global scheduler
    if scheduler and scheduler.state.id == project_id:
        if scheduler._runner and not scheduler._runner.done(): await scheduler.stop()
        scheduler.state.archived = True; STORE.save(scheduler.state); PROJECTS.touch(scheduler.state)
        scheduler = None
    try:
        PROJECTS.archive(project_id, True)
    except KeyError as exc:
        raise HTTPException(404, "Project not found") from exc
    return {"archived": True, "project_id": project_id}


@app.post("/api/projects/{project_id}/delete")
async def delete_project(project_id: str, request: ProjectDeleteRequest):
    global scheduler, STORE
    was_active = bool(scheduler and scheduler.state.id == project_id)
    if was_active and scheduler:
        if scheduler._runner and not scheduler._runner.done():
            await scheduler.stop()
        STORE.save(scheduler.state)
        PROJECTS.touch(scheduler.state)
        scheduler = None
        PROJECTS.set_active(None)
    try:
        return PROJECTS.delete(project_id, confirmation=request.confirmation, allow_active=was_active)
    except PermissionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "Project not found") from exc


@app.get("/api/continuity")
async def continuity_state():
    _require_scheduler()
    latest = STORE.latest_continuity() if hasattr(STORE, "latest_continuity") else None
    return latest or CONTINUITY.capture(scheduler.state, reason="api")


@app.get("/api/continuity/history")
async def continuity_history(limit: int = 20):
    _require_scheduler()
    if hasattr(STORE, "continuity_history"):
        return STORE.continuity_history(max(1, min(100, limit)))
    return []


@app.get("/api/goal-status")
async def goal_status():
    _require_scheduler()
    return GOAL_ENGINE.status(scheduler.state)


@app.get("/api/production-intelligence")
async def production_intelligence():
    _require_scheduler()
    return PRODUCTION_CORE.mission_control.snapshot(scheduler.state, persist=False)


@app.get("/api/engineering-readiness")
async def engineering_readiness():
    _require_scheduler()
    calibration = CONFIDENCE_CALIBRATION.report(scheduler.state)
    sop_library = scheduler.state.metadata.get("sop_library_v1", {})
    sop_count = sum(len(rows) for rows in sop_library.values())
    workspace = scheduler.state.metadata.get("workspace_v2", {})
    return {
        "version": "1.1.0-dev6-self-hosting-beta",
        "workspace": {"configured": bool(workspace), "schema_version": workspace.get("schema_version")},
        "confidence_calibration": calibration,
        "sop_candidates": sop_count,
        "workflow_strategies": len(scheduler.state.metadata.get("workflow_strategy_lab_v1", {})),
        "benchmark_suites": len(scheduler.state.metadata.get("benchmark_registry_v2", {})),
        "physical_windows_tests": "DEFERRED_BY_USER",
        "production_verified": False,
    }


@app.get("/api/quality-engineering")
async def quality_engineering():
    _require_scheduler()
    return QUALITY_ENGINEERING.project_snapshot(scheduler.state)


@app.get("/api/security-posture")
async def security_posture():
    _require_scheduler()
    return SECURITY_V2.threats.snapshot(scheduler.state)


@app.get("/api/memory/search")
async def memory_search(q: str, limit: int = 8):
    _require_scheduler()
    SEMANTIC_MEMORY.ingest_project(scheduler.state)
    return {"active": True, "items": SCALE_SECURITY.memory.relevance(scheduler.state, q, limit=max(1, min(25, int(limit))))}


@app.get("/api/scale-security")
async def scale_security():
    _require_scheduler()
    return SCALE_SECURITY.snapshot(scheduler.state)


@app.get("/api/release-candidate")
async def release_candidate():
    _require_scheduler()
    return RELEASE_CANDIDATE.snapshot(scheduler.state)


@app.get("/api/activity")
async def activity_state():
    _require_scheduler()
    return scheduler.metrics().get("activity", {})


@app.post("/api/resource-preset")
async def resource_preset(request: ResourcePresetRequest):
    _require_scheduler()
    try:
        OPERATOR_CONTROLS.set_resource(scheduler.state, request.preset)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    STORE.save(scheduler.state)
    return snapshot()


@app.post("/api/autonomy-profile")
async def autonomy_profile(request: AutonomyProfileRequest):
    _require_scheduler()
    try:
        OPERATOR_CONTROLS.set_autonomy(scheduler.state, request.level)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    STORE.save(scheduler.state)
    return snapshot()


@app.post("/api/operating-mode")
async def set_operating_mode(request: OperatingModeRequest):
    _require_scheduler()
    try:
        OPERATING_MODES.set(scheduler.state, request.mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    STORE.save(scheduler.state)
    return snapshot()


@app.get("/api/operator-controls")
async def operator_controls():
    _require_scheduler()
    return OPERATOR_CONTROLS.snapshot(scheduler.state)


@app.post("/api/power")
async def set_power(request: PowerRequest):
    _require_scheduler()
    scheduler.state.power_percent = request.power_percent
    scheduler.state.metadata["resource_preset"] = "custom"
    STORE.save(scheduler.state)
    return snapshot()


@app.post("/api/autonomy")
async def set_autonomy(request: ToggleRequest):
    _require_scheduler()
    scheduler.state.autonomy_enabled = request.enabled
    scheduler.state.metadata["autonomy_level"] = "balanced" if request.enabled else "supervised"
    scheduler.state.metadata["autonomy_threshold_delta"] = 0.0 if request.enabled else 0.20
    STORE.save(scheduler.state)
    return snapshot()


@app.post("/api/notifications")
async def set_notifications(request: ToggleRequest):
    _require_scheduler()
    scheduler.state.notifications_enabled = request.enabled
    STORE.save(scheduler.state)
    return snapshot()


@app.post("/api/pause")
async def pause():
    _require_scheduler()
    scheduler.state.paused = True
    STORE.save(scheduler.state)
    return snapshot()


@app.post("/api/resume")
async def resume():
    _require_scheduler()
    scheduler.state.paused = False
    scheduler.start()
    return snapshot()


@app.post("/api/decision/{decision_id}")
async def resolve_decision(decision_id: str, request: DecisionRequest):
    _require_scheduler()
    decision = scheduler.state.decisions.get(decision_id)
    if not decision or decision.status != DecisionStatus.OPEN:
        raise HTTPException(404, "Open decision not found")
    if request.selected not in decision.options:
        raise HTTPException(400, "Selected option is not valid")
    decision.selected = request.selected
    decision.status = DecisionStatus.USER_RESOLVED
    scheduler.state.human_interventions_required += 1
    scheduler.state.metadata.setdefault("decision_history", []).append({"id":decision.id,"selected":request.selected,"source":"user","recommendation":decision.recommendation})
    if scheduler.decision_learning:
        scheduler.decision_learning.record(situation=decision.title, recommendation=decision.recommendation, selected=request.selected, source="user")
    for task in scheduler.state.tasks.values():
        if task.metadata.get("decision_id") == decision_id and task.status == TaskStatus.NEEDS_REVIEW:
            if "pause" not in request.selected.lower():
                task.metadata["next_instruction"] = f"Proceed using the user's decision: {request.selected}"
                task.status = TaskStatus.READY
    STORE.save(scheduler.state)
    return snapshot()


@app.post("/api/work-settings")
async def set_work_settings(request: WorkSettingsRequest):
    _require_scheduler()
    for key in ("verification_percent", "depth_percent", "exploration_percent", "budget_limit", "priority_mode"):
        value = getattr(request, key)
        if value is not None:
            setattr(scheduler.state, key, value)
    STORE.save(scheduler.state)
    return snapshot()


@app.post("/api/absence/enter")
async def enter_absence():
    _require_scheduler(); AbsenceMode().enter(scheduler.state); STORE.save(scheduler.state); return snapshot()


@app.post("/api/absence/leave")
async def leave_absence():
    _require_scheduler(); report=AbsenceMode().leave(scheduler.state); STORE.save(scheduler.state); return {"state":snapshot(), "return_report":report}


@app.post("/api/goal/revise")
async def revise_goal(request: GoalRevisionRequest):
    _require_scheduler(); result=GoalRevisionManager().revise(scheduler.state, request.goal); STORE.save(scheduler.state); return {"state":snapshot(), "revision":result}


@app.post("/api/task/{task_id}/pause")
async def pause_branch(task_id: str):
    _require_scheduler(); count=SelectivePause().pause_branch(scheduler.state, task_id); STORE.save(scheduler.state); return {"affected":count, "state":snapshot()}


@app.post("/api/task/{task_id}/resume")
async def resume_branch(task_id: str):
    _require_scheduler(); count=SelectivePause().resume_branch(scheduler.state, task_id); STORE.save(scheduler.state); return {"affected":count, "state":snapshot()}


@app.get("/api/task/{task_id}")
async def task_detail(task_id: str):
    _require_scheduler(); task=scheduler.state.tasks.get(task_id)
    if not task: raise HTTPException(404, "Task not found")
    return task.model_dump(mode="json")


@app.get("/api/control-center")
async def control_center():
    _require_scheduler(); return CONTROL_CENTER.snapshot(scheduler.state)


@app.get("/api/project-map")
async def project_map():
    _require_scheduler(); return PROJECT_MAP.build(scheduler.state)


@app.get("/api/capacity-profile")
async def capacity_profile():
    _require_scheduler(); return asdict(CAPACITY.profile(scheduler.state))


@app.get("/api/recovery-audit")
async def recovery_audit():
    _require_scheduler(); return asdict(RECOVERY.audit(scheduler.state))


@app.get("/api/final-report")
async def final_report():
    _require_scheduler(); return {"report":FinalReportBuilder().build(scheduler.state)}


@app.get("/api/update/status")
async def update_status():
    manifest_url = os.getenv("CEO_UPDATE_MANIFEST_URL", "").strip()
    if not manifest_url:
        return {"configured": False, "available": False, "detail": "No update manifest configured."}
    try:
        result = await UPDATE_MANAGER.fetch_manifest(manifest_url, current_version=app.version)
        manifest = result["manifest"]
        return {"configured": True, "available": result["available"], "version": manifest.version, "channel": manifest.channel, "notes": manifest.notes}
    except Exception as exc:
        return {"configured": True, "available": False, "error": f"{type(exc).__name__}: {exc}"}


@app.get("/api/mobile-summary")
async def mobile_summary():
    if not scheduler:
        return {"active": False, "status": "idle"}
    state = scheduler.state; metrics = scheduler.metrics(); activity = metrics.get("activity", {})
    return {
        "active": True, "project_id": state.id, "goal": state.goal,
        "status": "completed" if state.completed_at else "paused" if state.paused else "working",
        "progress": state.progress, "eta_seconds": metrics.get("eta_seconds"),
        "active_workers": metrics.get("active_workers", 0),
        "needs_attention": len([t for t in state.leaf_tasks if t.status in {TaskStatus.FAILED, TaskStatus.NEEDS_REVIEW}]),
        "current": (activity.get("active") or [None])[0],
        "budget": metrics.get("budget", {}),
        "notifications": list(state.metadata.get("notifications", []))[-5:],
    }



@app.get("/api/desktop/preflight")
async def desktop_preflight():
    _require_scheduler(); return DESKTOP_BROWSER.local_preflight(scheduler.state)


@app.get("/api/desktop/applications")
async def desktop_applications():
    _require_scheduler(); DESKTOP_BROWSER.registry.discover(scheduler.state); return DESKTOP_BROWSER.snapshot(scheduler.state)


@app.get("/api/desktop/capabilities")
async def desktop_capabilities(required: str = ""):
    _require_scheduler(); wanted=[x.strip() for x in required.split(",") if x.strip()]; return {"required":wanted,"ranked":DESKTOP_BROWSER.capabilities.rank(scheduler.state,wanted)}

@app.get("/api/operator-autonomy")
async def operator_autonomy_status():
    _require_scheduler(); return OPERATIONAL_AUTONOMY.snapshot(scheduler.state)


@app.get("/api/operator-autonomy/preflight")
async def operator_autonomy_preflight():
    _require_scheduler(); return OPERATIONAL_AUTONOMY.preflight(scheduler.state)


@app.post("/api/operator-autonomy/device-route")
async def operator_autonomy_device_route(request: OperatorDeviceRouteRequest):
    _require_scheduler()
    return OPERATIONAL_AUTONOMY.router.recommend(
        task_kind=request.task_kind, estimated_ram_gb=request.estimated_ram_gb,
        requires_windows_ui=request.requires_windows_ui, mobile_available=request.mobile_available,
        mobile_ram_gb=request.mobile_ram_gb,
    )


@app.post("/api/operator-autonomy/friction-plan")
async def operator_autonomy_friction_plan(request: OperatorFrictionPlanRequest):
    _require_scheduler()
    result = OPERATIONAL_AUTONOMY.create_friction_tasks(scheduler.state, limit=request.limit)
    STORE.save(scheduler.state)
    return {"created": result, "count": len(result)}


@app.get("/api/self-hosting/preflight")
async def self_hosting_preflight():
    _require_scheduler(); return SELF_HOSTING.local_preflight(scheduler.state, providers)

@app.get("/api/self-hosting/status")
async def self_hosting_status():
    _require_scheduler(); return SELF_HOSTING.snapshot(scheduler.state, providers)

@app.get("/api/self-hosting/tools")
async def self_hosting_tools_status():
    _require_scheduler(); return SELF_HOSTING.tools.snapshot(scheduler.state)

@app.get("/api/self-hosting/evolution")
async def self_hosting_evolution_status():
    _require_scheduler(); return SELF_HOSTING.evolution.snapshot(scheduler.state)

@app.get("/api/self-hosting/evolution/preflight")
async def self_hosting_evolution_preflight():
    _require_scheduler(); return SELF_HOSTING.evolution.preflight(scheduler.state)

@app.post("/api/self-hosting/evolution/mission")
async def self_hosting_evolution_mission(request: SelfImprovementMissionRequest):
    _require_scheduler()
    mission = SELF_HOSTING.evolution.compiler.compile(
        scheduler.state,
        objective=request.objective,
        target_area=request.target_area,
        hypothesis=request.hypothesis,
        acceptance_criteria=request.acceptance_criteria,
        required_tests=request.required_tests,
    )
    STORE.save(scheduler.state)
    return asdict(mission)

@app.get("/api/self-hosting/alpha")
async def self_hosting_alpha_status():
    _require_scheduler(); return SELF_HOSTING.alpha.snapshot(scheduler.state)

@app.get("/api/self-hosting/alpha/preflight")
async def self_hosting_alpha_preflight():
    _require_scheduler(); return SELF_HOSTING.alpha.preflight(scheduler.state)

@app.post("/api/self-hosting/alpha/build")
async def self_hosting_alpha_build(request: SelfHostingCandidateBuildRequest):
    _require_scheduler()
    output = (DATA_DIR / "self_hosting_builds").resolve()
    try:
        result = SELF_HOSTING.alpha.builds.build(
            scheduler.state, request.candidate_root, output, mission_id=request.mission_id,
            version=request.version, running_root=Path(os.getenv("CEO_SELF_SOURCE_ROOT", str(ROOT))).resolve(),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Candidate build could not be generated: {exc}") from exc
    STORE.save(scheduler.state); return result

@app.post("/api/self-hosting/alpha/diff")
async def self_hosting_alpha_diff(request: SelfHostingReleaseDiffRequest):
    _require_scheduler()
    baseline = Path(os.getenv("CEO_SELF_SOURCE_ROOT", str(ROOT))).resolve()
    try:
        result = SELF_HOSTING.alpha.diff.compare(scheduler.state, baseline, request.candidate_root, mission_id=request.mission_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Release diff could not be generated: {exc}") from exc
    STORE.save(scheduler.state); return result

@app.post("/api/self-hosting/alpha/promotion-decision")
async def self_hosting_alpha_promotion_decision(request: SelfHostingPromotionDecisionRequest):
    _require_scheduler()
    if os.getenv("CEO_ENABLE_HUMAN_PROMOTION_API", "0") != "1":
        raise HTTPException(423, "Human promotion API is locked; enable it only from the trusted local operator UI")
    expected = os.getenv("CEO_HUMAN_PROMOTION_TOKEN", "")
    if not expected or not request.approval_token or not secrets.compare_digest(expected, request.approval_token):
        raise HTTPException(403, "Valid human promotion token required")
    try:
        result = SELF_HOSTING.alpha.promotion.decide(
            scheduler.state, mission_id=request.mission_id, decision=request.decision,
            human_confirmed=request.human_confirmed, actor="human", note=request.note,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Promotion decision rejected: {exc}") from exc
    STORE.save(scheduler.state); return result



@app.get("/api/self-hosting/beta")
async def self_hosting_beta_status():
    _require_scheduler(); return SELF_HOSTING.beta.snapshot(scheduler.state)


@app.get("/api/self-hosting/beta/preflight")
async def self_hosting_beta_preflight():
    _require_scheduler(); return SELF_HOSTING.beta.preflight(scheduler.state)


@app.post("/api/self-hosting/beta/session/start")
async def self_hosting_beta_session_start(request: SelfHostingSupervisedSessionRequest):
    _require_scheduler()
    result = SELF_HOSTING.beta.usage.start_session(
        scheduler.state, label=request.label, field_executed=request.field_executed,
        platform=request.platform, evidence=request.evidence,
    )
    STORE.save(scheduler.state); return result


@app.post("/api/self-hosting/beta/session/{session_id}/step")
async def self_hosting_beta_session_step(session_id: str, request: SelfHostingSupervisedStepRequest):
    _require_scheduler()
    try:
        result = SELF_HOSTING.beta.usage.record_step(scheduler.state, session_id, SupervisedStep(**request.model_dump()))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Supervised step rejected: {exc}") from exc
    STORE.save(scheduler.state); return result


@app.post("/api/self-hosting/beta/session/{session_id}/complete")
async def self_hosting_beta_session_complete(session_id: str):
    _require_scheduler()
    try:
        result = SELF_HOSTING.beta.complete_session(scheduler.state, session_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Supervised session could not be completed: {exc}") from exc
    STORE.save(scheduler.state); return result


@app.get("/api/self-hosting/beta/metrics")
async def self_hosting_beta_metrics():
    _require_scheduler(); return SELF_HOSTING.beta.metrics.measure(scheduler.state)


@app.get("/api/self-hosting/beta/friction")
async def self_hosting_beta_friction():
    _require_scheduler(); return {"items": SELF_HOSTING.beta.friction.backlog(scheduler.state)}


@app.get("/api/self-hosting/beta/permissions")
async def self_hosting_beta_permissions():
    _require_scheduler(); return SELF_HOSTING.beta.permissions.recommend(scheduler.state)


@app.post("/api/self-hosting/beta/permissions/apply")
async def self_hosting_beta_permissions_apply(request: SelfHostingPermissionApplyRequest):
    _require_scheduler()
    if os.getenv("CEO_ENABLE_PERMISSION_GRADUATION_API", "0") != "1":
        raise HTTPException(423, "Permission graduation API is locked; enable it only from the trusted local operator UI")
    expected = os.getenv("CEO_PERMISSION_GRADUATION_TOKEN", "")
    if not expected or not request.approval_token or not secrets.compare_digest(expected, request.approval_token):
        raise HTTPException(403, "Valid human permission token required")
    try:
        result = SELF_HOSTING.beta.permissions.apply(scheduler.state, target=request.target, human_confirmed=request.human_confirmed, actor="human")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Permission graduation rejected: {exc}") from exc
    STORE.save(scheduler.state); return result


@app.post("/api/self-hosting/workspace/create")
async def self_hosting_workspace_create(request: SelfHostingWorkspaceRequest):
    _require_scheduler()
    source_root = Path(os.getenv("CEO_SELF_SOURCE_ROOT", str(ROOT))).resolve()
    candidates_root = (DATA_DIR / "self_hosting_candidates").resolve()
    manager = SelfHostingWorkspace(source_root, candidates_root)
    try:
        result = manager.create(scheduler.state, label=request.label)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Self-hosting workspace could not be created: {exc}") from exc
    STORE.save(scheduler.state)
    return result

@app.post("/api/desktop/mode")
async def desktop_mode(request: DesktopModeRequest):
    _require_scheduler(); result = SELF_HOSTING.safety.set_mode(scheduler.state, request.mode); STORE.save(scheduler.state); return result

@app.post("/api/providers/openai/live-probe")
async def openai_live_probe():
    _require_scheduler()
    transport = None
    for provider in providers:
        candidate = getattr(provider, "transport", None)
        if candidate is not None and getattr(candidate, "name", "") == "openai-responses" and hasattr(candidate, "probe_live"):
            transport = candidate; break
    if transport is None:
        return {"status": "NOT_VERIFIED", "authenticated_live_verified": False, "reason": "openai_provider_not_configured"}
    result = await SELF_HOSTING.live.probe(scheduler.state, transport); STORE.save(scheduler.state); return result



@app.get("/api/self-hosting/field")
async def self_hosting_field_status():
    _require_scheduler(); return SELF_HOSTING.field.snapshot(scheduler.state)

@app.get("/api/self-hosting/field/preflight")
async def self_hosting_field_preflight():
    _require_scheduler(); return SELF_HOSTING.field.local_preflight(scheduler.state)

@app.get("/api/self-hosting/field/setup")
async def self_hosting_field_setup():
    _require_scheduler(); return SELF_HOSTING.field.setup.inspect(scheduler.state)

@app.get("/api/self-hosting/field/manifests")
async def self_hosting_field_manifests():
    _require_scheduler(); return {
        "windows": SELF_HOSTING.field.windows_manifest.snapshot(),
        "chrome": SELF_HOSTING.field.chrome_manifest.snapshot(),
        "chatgpt": SELF_HOSTING.field.chatgpt_manifest.snapshot(),
    }

@app.post("/api/self-hosting/emergency-stop")
async def self_hosting_emergency_stop(request: EmergencyStopRequest):
    _require_scheduler(); result = SELF_HOSTING.field.emergency.stop(scheduler.state, reason=request.reason, actor="human"); STORE.save(scheduler.state); return result

@app.post("/api/self-hosting/safe-resume")
async def self_hosting_safe_resume(request: SafeResumeRequest):
    _require_scheduler()
    try:
        result = SELF_HOSTING.field.resume.resume(scheduler.state, pending_actions=request.pending_actions, human_confirmed=request.human_confirmed)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Safe resume rejected: {exc}") from exc
    STORE.save(scheduler.state); return result

@app.get("/api/validation")
async def validation_state():
    """Evidence-backed maturity matrix. Synthetic tests can never masquerade as live validation."""
    return {"summary": VALIDATION.summary(), "matrix": VALIDATION.matrix(), "release_gates": VALIDATION_GATES.assess(VALIDATION)}


@app.post("/api/export")
async def export_project():
    _require_scheduler(); path=DATA_DIR/f"project-{scheduler.state.id}.ceo.zip"; ProjectExporter().export(scheduler.state,path); return {"path":str(path)}


def _require_scheduler() -> None:
    if not scheduler:
        raise HTTPException(409, "No active project")


def task_view(task_id: str):
    task = scheduler.state.tasks[task_id]
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "provider": task.provider_name,
        "conversation_turns": task.conversation_turns,
        "verified": bool(task.metadata.get("verified", False)),
        "verification_summary": task.metadata.get("verification_summary", {}),
        "children": [task_view(cid) for cid in task.children if cid in scheduler.state.tasks],
    }


def snapshot():
    global _catalog_touch_ts
    if not scheduler:
        return {"active": False, "provider_names": [p.name for p in providers]}
    state = scheduler.state
    now = time.monotonic()
    if now - _catalog_touch_ts > 5.0:
        try: PROJECTS.touch(state)
        except Exception: pass
        _catalog_touch_ts = now
    open_decisions = [d.model_dump(mode="json") for d in state.decisions.values() if d.status == DecisionStatus.OPEN]
    return {
        "active": True,
        "project_id": state.id,
        "project_name": state.project_name or state.goal[:80],
        "goal": state.goal,
        "goal_status": GOAL_ENGINE.status(state),
        "power_percent": state.power_percent,
        "paused": state.paused,
        "completed_at": state.completed_at,
        "autonomy_enabled": state.autonomy_enabled,
        "notifications_enabled": state.notifications_enabled,
        "provider_names": [p.name for p in providers],
        "metrics": scheduler.metrics(),
        "tree": [task_view(root_id) for root_id in state.root_task_ids],
        "decisions": open_decisions,
        "notifications": list(state.metadata.get("notifications", []))[-20:],
        "work_settings": {"verification_percent":state.verification_percent,"depth_percent":state.depth_percent,"exploration_percent":state.exploration_percent,"budget_limit":state.budget_limit,"priority_mode":state.priority_mode},
        "absence_mode": state.absence_mode,
        "operator_controls": OPERATOR_CONTROLS.snapshot(state),
        "continuity": state.metadata.get("continuity_snapshot") or CONTINUITY.capture(state, reason="snapshot"),
        "quality_engineering": QUALITY_ENGINEERING.project_snapshot(state),
        "desktop_browser": DESKTOP_BROWSER.snapshot(state),
        "self_hosting": SELF_HOSTING.snapshot(state, providers),
        "operational_autonomy": OPERATIONAL_AUTONOMY.snapshot(state),
        "real_work_queue": REAL_WORK_QUEUE.snapshot(state, limit=50),
        "production_intelligence": {
            "health": PRODUCTION_CORE.mission_control.health(state),
            "autonomy_confidence": AUTONOMY_CONFIDENCE.score(state),
            "recommended_strategy": state.metadata.get("probabilistic_plan", {}).get("recommended"),
            "evidence_records": len(state.metadata.get("evidence_ledger_v2", [])),
            "verification": PRODUCTION_CORE.verification.project_summary(state),
            "security": SECURITY_V2.threats.snapshot(state),
            "operating_mode": state.metadata.get("operating_mode_v1", {}).get("mode", "normal"),
            "confidence_calibration": CONFIDENCE_CALIBRATION.report(state),
            "sop_candidates": sum(len(rows) for rows in state.metadata.get("sop_library_v1", {}).values()),
        },
        "exceptions": [{"id":t.id,"title":t.title,"status":t.status.value,"provider":t.provider_name,"stage":t.metadata.get("provider_stage")} for t in state.leaf_tasks if t.status in {TaskStatus.FAILED,TaskStatus.NEEDS_REVIEW}][:50],
    }


def _launcher_log(message: str) -> None:
    """Best-effort launcher trace for windowed/frozen Windows builds."""
    try:
        log_dir = Path(DATA_DIR) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "launcher.log").open("a", encoding="utf-8") as fh:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            fh.write(f"{stamp} {message}\n")
    except Exception:
        pass


def _windows_app_browser_candidates() -> list[Path]:
    """Return likely Chromium-family browser executables for app-window mode.

    CEO is a local web UI, but the Windows product should feel like a desktop
    application.  Edge/Chrome ``--app=URL`` gives us a dedicated top-level
    window instead of reusing a hidden/background browser tab.
    """
    candidates: list[Path] = []
    roots = [
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("PROGRAMFILES"),
        os.environ.get("LOCALAPPDATA"),
    ]
    suffixes = [
        Path("Microsoft/Edge/Application/msedge.exe"),
        Path("Google/Chrome/Application/chrome.exe"),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root)
        for suffix in suffixes:
            candidate = base / suffix
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _open_windows_app_window(url: str) -> bool:
    """Open CEO in a dedicated Edge/Chrome app window when available."""
    if os.name != "nt":
        return False

    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for browser in _windows_app_browser_candidates():
        try:
            if not browser.is_file():
                continue
            subprocess.Popen(
                [str(browser), f"--app={url}", "--start-maximized"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                close_fds=False,
            )
            _launcher_log(f"desktop app window opened with {browser}")
            return True
        except Exception as exc:
            _launcher_log(f"app-window launch failed for {browser}: {exc!r}")
    _launcher_log("no Edge/Chrome executable found for app-window mode")
    return False


def _open_url_via_windows_shell(url: str) -> bool:
    """Open CEO visibly, preferring a dedicated desktop app window.

    On physical Windows testing, opening the URL through the normal browser
    association could reuse an existing background tab, making a successful
    launch look like nothing happened.  Prefer Edge/Chrome ``--app`` mode and
    keep shell/browser fallbacks for machines where neither executable is
    discoverable.
    """
    if os.name == "nt":
        if _open_windows_app_window(url):
            return True

        try:
            import ctypes

            result = ctypes.windll.shell32.ShellExecuteW(None, "open", url, None, None, 1)
            if int(result) > 32:
                _launcher_log(f"ShellExecuteW opened {url}")
                return True
            _launcher_log(f"ShellExecuteW returned failure code {int(result)}")
        except Exception as exc:
            _launcher_log(f"ShellExecuteW exception: {exc!r}")

        try:
            flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            subprocess.Popen(
                ["cmd.exe", "/d", "/c", "start", "", url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                close_fds=False,
            )
            _launcher_log(f"cmd start opened {url}")
            return True
        except Exception as exc:
            _launcher_log(f"cmd start exception: {exc!r}")

    try:
        opened = bool(webbrowser.open(url, new=1, autoraise=True))
        _launcher_log(f"webbrowser.open returned {opened} for {url}")
        return opened
    except Exception as exc:
        _launcher_log(f"webbrowser exception: {exc!r}")
        return False


def _open_desktop_ui_when_ready(
    url: str = "http://127.0.0.1:8765",
    *,
    timeout_seconds: float = 30.0,
) -> None:
    """Open the local CEO UI once the packaged server is actually reachable."""
    if os.environ.get("CEO_NO_AUTO_OPEN", "").strip().lower() in {"1", "true", "yes", "on"}:
        _launcher_log("auto-open suppressed by CEO_NO_AUTO_OPEN")
        return

    _launcher_log(
        f"launcher scheduled; frozen={bool(getattr(sys, 'frozen', False))}; "
        f"python={sys.version.split()[0]}; url={url}"
    )

    def _wait_and_open() -> None:
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=0.75) as response:
                    status = int(getattr(response, "status", 200))
                    if 200 <= status < 500:
                        _launcher_log(f"server reachable with HTTP {status}")
                        if not _open_url_via_windows_shell(url):
                            _launcher_log("all URL launch methods failed")
                        return
            except Exception as exc:
                last_error = exc
                time.sleep(0.2)
        _launcher_log(f"server not reachable before timeout; last_error={last_error!r}")

    threading.Thread(target=_wait_and_open, name="ceo-ui-launcher", daemon=True).start()

def _uvicorn_file_log_config(data_dir: Path = DATA_DIR) -> dict:
    """Logging config safe for PyInstaller windowed executables.

    Uvicorn's default color formatter probes ``sys.stderr.isatty()``.  In a
    ``console=False`` PyInstaller executable stdout/stderr can be ``None``,
    which makes the default formatter crash before the server starts.  The
    desktop build therefore logs to a rotating file using the stdlib
    formatter and never depends on a console stream.
    """
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ceo.log"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
            }
        },
        "handlers": {
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "filename": str(log_file),
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 3,
                "encoding": "utf-8",
                "delay": True,
            }
        },
        "loggers": {
            "uvicorn": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["file"], "level": "INFO", "propagate": False},
        },
    }


if __name__ == "__main__":
    import uvicorn
    # A windowed PyInstaller build has no console, so explicitly surface the
    # local web UI after the server is listening.
    _open_desktop_ui_when_ready()
    # Pass the app object directly in the frozen desktop build.  There is no
    # reload/multiprocess import cycle to justify a module string here.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8765,
        reload=False,
        log_config=_uvicorn_file_log_config(),
    )
