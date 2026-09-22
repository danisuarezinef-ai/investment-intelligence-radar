package ai.ceo.android

import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class M05AShellUiTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun mainShellShowsGoalStatusAndProgress() {
        composeRule.onNodeWithText("CEO App").fetchSemanticsNode()
        composeRule.onNodeWithText("Goal Engine").fetchSemanticsNode()
        composeRule.onNodeWithText("Estado general").fetchSemanticsNode()
        composeRule.onNodeWithText("Progreso").fetchSemanticsNode()
        composeRule.onNodeWithContentDescription("progress-percent")
            .assertTextContains("0%")
    }

    @Test
    fun goalObjectiveStartsCollapsedAndCanExpand() {
        val before = composeRule
            .onAllNodesWithContentDescription("goal-objective")
            .fetchSemanticsNodes()
        assertTrue(before.isEmpty())

        composeRule.onNodeWithContentDescription("goal-toggle").performClick()

        val after = composeRule
            .onAllNodesWithContentDescription("goal-objective")
            .fetchSemanticsNodes()
        assertTrue(after.isNotEmpty())
        composeRule.onNodeWithText("Ocultar objetivo").fetchSemanticsNode()
    }

    @Test
    fun goalCanBePreparedFromTheHomeShell() {
        composeRule.onNodeWithContentDescription("goal-title")
            .performTextInput("Primera tarea")
        composeRule.onNodeWithContentDescription("goal-toggle").performClick()
        composeRule.onNodeWithContentDescription("goal-objective")
            .performTextInput("Completar una tarea sencilla de principio a fin")
        composeRule.onNodeWithContentDescription("goal-save").performClick()

        composeRule.onNodeWithText("Objetivo guardado").fetchSemanticsNode()
        composeRule.onNodeWithContentDescription("general-status")
            .assertTextContains("Objetivo preparado")
        composeRule.onNodeWithContentDescription("progress-percent")
            .assertTextContains("0%")
    }
}
