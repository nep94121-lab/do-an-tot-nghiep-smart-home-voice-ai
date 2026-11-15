package vn.edu.hust.seee.smarthome.ui.main

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import vn.edu.hust.seee.smarthome.data.DataRepository
import vn.edu.hust.seee.smarthome.ui.main.models.AutomationRuleItem
import vn.edu.hust.seee.smarthome.ui.main.models.AutomationSnapshotState
import vn.edu.hust.seee.smarthome.ui.main.models.ClockScheduleItem
import vn.edu.hust.seee.smarthome.ui.main.models.CountdownTimerItem
import vn.edu.hust.seee.smarthome.ui.main.models.CustomSceneItem

class MainScreenViewModel(private val dataRepository: DataRepository) : ViewModel() {
  val uiState: StateFlow<MainScreenUiState> =
    combine<List<String>, AutomationSnapshotState, MainScreenUiState>(
      dataRepository.data,
      dataRepository.automationSnapshot,
    ) { items, auto ->
      MainScreenUiState.Success(
        data = items,
        activeTimers = auto.activeTimers,
        clockSchedules = auto.clockSchedules,
        automationRules = auto.automationRules,
        customScenes = auto.customScenes,
      )
    }
      .catch { emit(MainScreenUiState.Error(it)) }
      .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), MainScreenUiState.Loading)

  fun updateAutomationSnapshot(snapshot: AutomationSnapshotState) {
    dataRepository.updateAutomationSnapshot(snapshot)
  }
}

sealed interface MainScreenUiState {
  object Loading : MainScreenUiState

  data class Error(val throwable: Throwable) : MainScreenUiState

  data class Success(
    val data: List<String>,
    val activeTimers: List<CountdownTimerItem> = emptyList(),
    val clockSchedules: List<ClockScheduleItem> = emptyList(),
    val automationRules: List<AutomationRuleItem> = emptyList(),
    val customScenes: List<CustomSceneItem> = emptyList(),
  ) : MainScreenUiState
}
