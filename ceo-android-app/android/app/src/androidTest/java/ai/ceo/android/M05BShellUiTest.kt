package ai.ceo.android

import android.content.pm.ActivityInfo
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class M05BShellUiTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun navigationShowsHomeTasksAndDecisions() {
        composeRule.onNodeWithContentDescription("nav-home").fetchSemanticsNode()
        composeRule.onNodeWithContentDescription("nav-tasks").fetchSemanticsNode()
        composeRule.onNodeWithContentDescription("nav-decisions").fetchSemanticsNode()

        composeRule.onNodeWithContentDescription("nav-tasks").performClick()
        composeRule.onNodeWithText("Tareas activas").fetchSemanticsNode()
        composeRule.onNodeWithContentDescription("active-tasks-screen").fetchSemanticsNode()

        composeRule.onNodeWithContentDescription("nav-decisions").performClick()
        composeRule.onNodeWithText("Propuestas y decisiones").fetchSemanticsNode()
        composeRule.onNodeWithContentDescription("decisions-screen").fetchSemanticsNode()

        composeRule.onNodeWithContentDescription("nav-home").performClick()
        composeRule.onNodeWithText("Goal Engine").fetchSemanticsNode()
    }

    @Test
    fun preparedGoalAppearsAsPendingTaskWithoutFakeExecution() {
        composeRule.onNodeWithContentDescription("nav-home").performClick()
        composeRule.onNodeWithContentDescription("goal-title").performTextClearance()
        composeRule.onNodeWithContentDescription("goal-title").performTextInput("M05 tarea")

        val objectiveVisible = composeRule
            .onAllNodesWithContentDescription("goal-objective")
            .fetchSemanticsNodes()
            .isNotEmpty()
        if (!objectiveVisible) {
            composeRule.onNodeWithContentDescription("goal-toggle").performClick()
        }

        composeRule.onNodeWithContentDescription("goal-objective").performTextClearance()
        composeRule.onNodeWithContentDescription("goal-objective")
            .performTextInput("Validar una tarea preparada sin simular ejecución")
        composeRule.onNodeWithContentDescription("goal-save").performClick()

        composeRule.onNodeWithContentDescription("nav-tasks").performClick()
        composeRule.onNodeWithText("Tarea preparada").fetchSemanticsNode()
        composeRule.onNodeWithContentDescription("prepared-task-title")
            .assertTextContains("M05 tarea")
        composeRule.onNodeWithContentDescription("prepared-task-status")
            .assertTextContains("Pendiente")
        composeRule.onNodeWithContentDescription("task-count")
            .assertTextContains("1 tarea")
        composeRule.onNodeWithText(
            "Preparada, pero no iniciada. CEO no simula progreso antes de M07."
        ).fetchSemanticsNode()
    }

    @Test
    fun proposalsCanBeSelectedAndCustomProposalAdded() {
        composeRule.onNodeWithContentDescription("nav-decisions").performClick()

        composeRule.onNodeWithContentDescription("decision-proposal-0").performClick()
        composeRule.onNodeWithContentDescription("selected-decision")
            .assertTextContains("Priorizar calidad")

        composeRule.onNodeWithContentDescription("decision-custom-input")
            .performTextInput("Propuesta propia M05")
        composeRule.onNodeWithContentDescription("decision-add-custom").performClick()

        composeRule.onNodeWithContentDescription("selected-decision")
            .assertTextContains("Propuesta propia M05")
        composeRule.onNodeWithContentDescription("custom-proposal-0").fetchSemanticsNode()
    }

    @Test
    fun shellAdaptsToLandscapeExpandedLayout() {
        composeRule.activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
        composeRule.waitUntil(timeoutMillis = 10_000) {
            composeRule
                .onAllNodesWithContentDescription("layout-expanded")
                .fetchSemanticsNodes()
                .isNotEmpty()
        }
        assertTrue(
            composeRule
                .onAllNodesWithContentDescription("layout-expanded")
                .fetchSemanticsNodes()
                .isNotEmpty()
        )
        composeRule.onNodeWithContentDescription("nav-home").fetchSemanticsNode()
        composeRule.onNodeWithContentDescription("nav-tasks").fetchSemanticsNode()
        composeRule.onNodeWithContentDescription("nav-decisions").fetchSemanticsNode()
    }
}
