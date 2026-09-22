from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "ceo-android-app" / "android"


def read(rel: str) -> str:
    path = ANDROID / rel
    assert path.is_file(), f"missing {rel}"
    return path.read_text(encoding="utf-8")


def main() -> None:
    main_activity = read("app/src/main/java/ai/ceo/android/MainActivity.kt")
    home = read("app/src/main/java/ai/ceo/android/CEOHomeScreen.kt")
    gradle = read("app/build.gradle.kts")
    split = json.loads((ROOT / "ceo-android-app/M05_SPLIT_PLAN.json").read_text(encoding="utf-8"))

    assert split["current_focus"] == "M05-A"
    assert split["physical_installation_allowed"] is False

    # APP031 — real home screen wired from the launcher activity.
    assert "CEOHomeScreen(" in main_activity
    assert 'Text("CEO App"' in home
    assert '"Control central"' in home
    assert "verticalScroll(rememberScrollState())" in home

    # APP032 — Goal Engine title always visible, objective hidden until user action.
    assert 'Text("Goal Engine"' in home
    assert 'label = { Text("Título del objetivo") }' in home
    assert 'Text(if (expanded) "Ocultar objetivo" else "Mostrar objetivo")' in home
    assert 'if (expanded)' in home
    assert 'label = { Text("Objetivo activo") }' in home
    assert 'Text("Guardar objetivo")' in home
    assert 'contentDescription = "goal-title"' in home
    assert 'contentDescription = "goal-objective"' in home
    assert 'contentDescription = "goal-toggle"' in home

    # APP033 — general state surface.
    assert 'Text("Estado general"' in home
    assert '"Objetivo preparado"' in home
    assert '"Objetivo en edición"' in home
    assert '"Esperando objetivo"' in home
    assert 'contentDescription = "general-status"' in home

    # APP034 — progress and percentage surface.
    assert 'Text("Progreso"' in home
    assert 'LinearProgressIndicator(' in home
    assert 'contentDescription = "progress-percent"' in home
    assert 'contentDescription = "goal-progress"' in home
    assert 'mutableIntStateOf(0)' in home

    # Interactive UI test dependencies are mandatory for this block.
    assert 'androidx.compose.ui:ui-test-junit4' in gradle
    assert 'androidx.compose.ui:ui-test-manifest' in gradle
    ui_test = ANDROID / "app/src/androidTest/java/ai/ceo/android/M05AShellUiTest.kt"
    assert ui_test.is_file()
    test_text = ui_test.read_text(encoding="utf-8")
    assert "goalObjectiveStartsCollapsedAndCanExpand" in test_text
    assert "goalCanBePreparedFromTheHomeShell" in test_text
    assert "mainShellShowsGoalStatusAndProgress" in test_text

    result = {
        "schema_version": 1,
        "status": "M05A_SOURCE_CONTRACT_PASS",
        "APP031": "SOURCE_PASS",
        "APP032": "SOURCE_PASS",
        "APP033": "SOURCE_PASS",
        "APP034": "SOURCE_PASS",
        "interactive_emulator_test_required": True,
        "m05b_started": False,
        "physical_installation_allowed": False,
    }
    (ROOT / "ceo-android-app/M05A_SOURCE_VERIFICATION.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    print("M05A_SOURCE_CONTRACT_PASS")


if __name__ == "__main__":
    main()
