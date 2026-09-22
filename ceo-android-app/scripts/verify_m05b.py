from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "ceo-android-app" / "android"


def read(rel: str) -> str:
    p = ANDROID / rel
    assert p.is_file(), f"missing {rel}"
    return p.read_text(encoding="utf-8")


def main() -> None:
    main = read("app/src/main/java/ai/ceo/android/MainActivity.kt")
    shell = read("app/src/main/java/ai/ceo/android/CEOAppShell.kt")
    theme = read("app/src/main/java/ai/ceo/android/CEOAppTheme.kt")
    home = read("app/src/main/java/ai/ceo/android/CEOHomeScreen.kt")
    test = read("app/src/androidTest/java/ai/ceo/android/M05BShellUiTest.kt")
    split = json.loads((ROOT / "ceo-android-app/M05_SPLIT_PLAN.json").read_text(encoding="utf-8"))

    assert split["split"]["M05-A"]["status"] == "M05A_COMPLETE_EMULATOR_VERIFIED"
    assert split["split"]["M05-B"]["status"] == "PENDING_SEPARATE_ATTACK"
    assert split["physical_installation_allowed"] is False

    # APP035 — active tasks surface, honest pre-M07 state.
    assert "ActiveTasksScreen(" in shell
    assert 'Text("Tareas activas"' in shell
    assert '"Sin tareas activas"' in shell
    assert '"Tarea preparada"' in shell
    assert '"Pendiente · motor M07"' in shell
    assert "CEO no simula progreso antes de M07." in shell
    assert 'contentDescription = "active-tasks-screen"' in shell
    assert 'contentDescription = "prepared-task-status"' in shell
    assert 'contentDescription = "task-count"' in shell

    # APP036 — proposals / decisions plus freeform proposal.
    assert "DecisionsScreen()" in shell
    assert 'Text("Propuestas y decisiones"' in shell
    assert '"Priorizar calidad"' in shell
    assert '"Priorizar rapidez"' in shell
    assert '"Pedir revisión antes de cerrar"' in shell
    assert 'label = { Text("Propuesta:") }' in shell
    assert 'contentDescription = "decision-custom-input"' in shell
    assert 'contentDescription = "decision-add-custom"' in shell
    assert 'contentDescription = "selected-decision"' in shell
    assert '"Pendiente de conexión operativa en M07."' in shell

    # APP037 — explicit home/tasks/decisions navigation.
    assert "enum class CEOSection" in shell
    assert 'HOME("Inicio"' in shell
    assert 'TASKS("Tareas"' in shell
    assert 'DECISIONS("Decisiones"' in shell
    assert "NavigationBar" in shell
    assert "NavigationRail" in shell
    assert '"nav-' in shell
    assert "CEOAppShell(" in main
    assert "CEOHomeScreen(" in shell

    # APP038 — system light/dark theme and responsive breakpoint.
    assert "CEOAppTheme {" in main
    assert "isSystemInDarkTheme()" in theme
    assert "darkColorScheme()" in theme
    assert "lightColorScheme()" in theme
    assert "BoxWithConstraints" in shell
    assert "maxWidth >= 700.dp" in shell
    assert '"layout-expanded"' in shell
    assert '"layout-compact"' in shell
    assert '"Tema oscuro activo"' in shell
    assert '"Tema claro activo"' in shell

    # Preserve M05-A features.
    assert "GoalEngineCard(" in home
    assert 'Text("Estado general"' in home
    assert 'Text("Progreso"' in home

    # Runtime tests must exercise all new surfaces.
    for name in [
        "navigationShowsHomeTasksAndDecisions",
        "preparedGoalAppearsAsPendingTaskWithoutFakeExecution",
        "proposalsCanBeSelectedAndCustomProposalAdded",
        "shellAdaptsToLandscapeExpandedLayout",
    ]:
        assert name in test, name

    forbidden_runtime_claims = [
        "task_execution_enabled = true",
        "INTERNAL_DOWNLOAD_ALLOWED = true",
        "INSTALL_HANDOFF_ALLOWED = true",
        "SILENT_INSTALL_ALLOWED = true",
    ]
    joined = "\n".join([shell, theme, main])
    for item in forbidden_runtime_claims:
        assert item not in joined, item

    result = {
        "schema_version": 1,
        "status": "M05B_SOURCE_CONTRACT_PASS",
        "APP035": "SOURCE_PASS",
        "APP036": "SOURCE_PASS",
        "APP037": "SOURCE_PASS",
        "APP038": "SOURCE_PASS",
        "runtime_emulator_required": True,
        "task_engine_active": False,
        "updater_activation_allowed": False,
        "physical_installation_allowed": False,
    }
    (ROOT / "ceo-android-app/M05B_SOURCE_VERIFICATION.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    print("M05B_SOURCE_CONTRACT_PASS")


if __name__ == "__main__":
    main()
