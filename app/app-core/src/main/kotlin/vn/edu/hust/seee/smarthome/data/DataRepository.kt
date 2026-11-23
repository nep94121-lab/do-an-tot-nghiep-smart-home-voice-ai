package vn.edu.hust.seee.smarthome.data

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flow
import vn.edu.hust.seee.smarthome.ui.main.models.AutomationSnapshotState

interface DataRepository {
  val data: Flow<List<String>>
  val automationSnapshot: Flow<AutomationSnapshotState>
    get() = flow { emit(AutomationSnapshotState()) }

  fun updateAutomationSnapshot(snapshot: AutomationSnapshotState) {}
}

class DefaultDataRepository : DataRepository {
  override val data: Flow<List<String>> = flow { emit(listOf("Android")) }

  private val _automationSnapshot = MutableStateFlow(AutomationSnapshotState())
  override val automationSnapshot: Flow<AutomationSnapshotState> = _automationSnapshot.asStateFlow()

  override fun updateAutomationSnapshot(snapshot: AutomationSnapshotState) {
    _automationSnapshot.value = snapshot
  }
}
