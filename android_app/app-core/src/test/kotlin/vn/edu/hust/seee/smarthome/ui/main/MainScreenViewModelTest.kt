package vn.edu.hust.seee.smarthome.ui.main

import junit.framework.TestCase.assertEquals
import junit.framework.TestCase.assertTrue
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.runTest
import org.junit.Test
import vn.edu.hust.seee.smarthome.data.DataRepository
import vn.edu.hust.seee.smarthome.data.DefaultDataRepository
import vn.edu.hust.seee.smarthome.ui.main.models.AutomationRuleItem
import vn.edu.hust.seee.smarthome.ui.main.models.AutomationSnapshotState
import vn.edu.hust.seee.smarthome.ui.main.models.ClockScheduleItem
import vn.edu.hust.seee.smarthome.ui.main.models.CountdownTimerItem
import vn.edu.hust.seee.smarthome.ui.main.models.CustomSceneItem
import vn.edu.hust.seee.smarthome.ui.main.models.CustomSceneStep
import vn.edu.hust.seee.smarthome.ui.main.models.canonicalDeviceAction
import vn.edu.hust.seee.smarthome.ui.main.models.canonicalWhenState
import vn.edu.hust.seee.smarthome.ui.main.models.formatDeviceActionLabel

class MainScreenViewModelTest {
  @Test
  fun uiState_initiallyLoading() = runTest {
    val viewModel = MainScreenViewModel(FakeMyModelRepository())
    assertEquals(viewModel.uiState.first(), MainScreenUiState.Loading)
  }

  @Test
  fun uiState_onItemSaved_isDisplayed() = runTest {
    val viewModel = MainScreenViewModel(FakeMyModelRepository())
    assertEquals(viewModel.uiState.first(), MainScreenUiState.Loading)
  }

  @Test
  fun uiState_exposesUpdatedAutomationSnapshot() = runTest {
    val repo = DefaultDataRepository()
    val viewModel = MainScreenViewModel(repo)
    val snapshot = AutomationSnapshotState(
      activeTimers = listOf(
        CountdownTimerItem(
          id = "tm_1",
          deviceId = "living_room_light",
          deviceName = "Đèn phòng khách",
          targetStateOn = true,
          remainingSeconds = 30,
        )
      ),
      clockSchedules = listOf(
        ClockScheduleItem(
          id = "sched_1",
          deviceId = "bedroom_light",
          deviceName = "Đèn phòng ngủ",
          action = "turn_off",
          timeHhmm = "22:30",
          scheduleType = "daily",
        )
      ),
      automationRules = listOf(
        AutomationRuleItem(
          id = "rule_1",
          whenDeviceId = "main_door",
          whenDeviceName = "Cửa chính",
          whenState = "OPEN",
          thenDeviceId = "living_room_light",
          thenDeviceName = "Đèn phòng khách",
          thenAction = "turn_on",
        )
      ),
      customScenes = listOf(
        CustomSceneItem(
          id = "scene_1",
          phrase = "Đi ngủ",
          steps = listOf(CustomSceneStep("living_room_light", "turn_off")),
          stepsSummary = "Tắt Đèn phòng khách",
        )
      ),
    )

    repo.updateAutomationSnapshot(snapshot)
    val successState = viewModel.uiState.first { it is MainScreenUiState.Success } as MainScreenUiState.Success
    assertEquals(1, successState.activeTimers.size)
    assertEquals("sched_1", successState.clockSchedules.first().scheduleId)
    assertEquals("rule_1", successState.automationRules.first().ruleId)
    assertEquals("scene_1", successState.customScenes.first().commandId)
    assertTrue(successState.customScenes.first().enabled)
  }

  @Test
  fun domainHelpers_mapDoorAndStandardDevicesCleanly() {
    assertEquals("open", canonicalDeviceAction("main_door", true))
    assertEquals("close", canonicalDeviceAction("main_door", false))
    assertEquals("turn_on", canonicalDeviceAction("fan", true))
    assertEquals("turn_off", canonicalDeviceAction("fan", false))

    assertEquals("OPEN", canonicalWhenState("main_door", true))
    assertEquals("CLOSED", canonicalWhenState("main_door", false))
    assertEquals("ON", canonicalWhenState("ac", true))
    assertEquals("OFF", canonicalWhenState("ac", false))

    assertEquals("Mở Cửa chính", formatDeviceActionLabel("main_door", "Cửa chính", "open"))
    assertEquals("Khóa Cửa chính", formatDeviceActionLabel("main_door", "Cửa chính", "close"))
    assertEquals("Bật Quạt trần", formatDeviceActionLabel("fan", "Quạt trần", "turn_on"))
    assertEquals("Tắt Quạt trần", formatDeviceActionLabel("fan", "Quạt trần", "turn_off"))
  }
}

private class FakeMyModelRepository : DataRepository {
  override val data: Flow<List<String>> = flow { emit(listOf("Sample")) }
}
