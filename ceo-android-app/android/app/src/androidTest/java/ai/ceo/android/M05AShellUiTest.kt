package ai.ceo.android

import androidx.compose.ui.test.assertDoesNotExist
import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import org.junit.Rule
import org.junit.Test

class M05AShellUiTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun mainShellShowsGoalStatusAndProgress() {
        composeRule.onNodeWithText("CEO App").assertExists()
        composeRule.onNodeWithText("Goal Engine").assertExists()
        composeRule.onNodeWithText("Estado general").assertExists()
        composeRule.onNodeWithText("Progreso").assertExists()
        composeRule.onNodeWithContentDescription("progress-percent")
            .assertTextContains("0%")
    }

    @Test
    fun goalObjectiveStartsCollapsedAndCanExpand() {
        composeRule.onNodeWithContentDescription("goal-objective").assertDoesNotExist()
        composeRule.onNodeWithContentDescription("goal-toggle").performClick()
        composeRule.onNodeWithContentDescription("goal-objective").assertExists()
        composeRule.onNodeWithText("Ocultar objetivo").assertExists()
    }

    @Test
    fun goalCanBePreparedFromTheHomeShell() {
        composeRule.onNodeWithContentDescription("goal-title")
            .performTextInput("Primera tarea")
        composeRule.onNodeWithContentDescription("goal-toggle").performClick()
        composeRule.onNodeWithContentDescription("goal-objective")
            .performTextInput("Completar una tarea sencilla de principio a fin")
        composeRule.onNodeWithContentDescription("goal-save").performClick()

        composeRule.onNodeWithText("Objetivo guardado").assertExists()
        composeRule.onNodeWithContentDescription("general-status")
            .assertTextContains("Objetivo preparado")
        composeRule.onNodeWithContentDescription("progress-percent")
            .assertTextContains("0%")
    }
}
