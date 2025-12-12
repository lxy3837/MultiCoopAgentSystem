# 核心类：StateManager（全局状态管理器）
from dataclasses import dataclass, field
from datetime import datetime
from data.data_manager import DataManager


@dataclass
class StateManager:
    """全局状态管理器：跟踪所有Agent/任务状态"""
    agents: dict = field(default_factory=dict)  # {agent_id: Agent实例}
    pending_tasks: list = field(default_factory=list)
    running_tasks: list = field(default_factory=list)
    completed_tasks: list = field(default_factory=list)
    data_manager: DataManager = field(default_factory=DataManager)
    updated_at: datetime = field(default_factory=datetime.now)

    def register_agent(self, agent):
        """注册Agent到状态管理器"""
        self.agents[agent.agent_id] = agent
        self.updated_at = datetime.now()

    def unregister_agent(self, agent_id: str):
        """注销Agent"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            self.updated_at = datetime.now()

    def update_task_status(self, task_id: str, status: str):
        """更新任务状态（同步到数据管理器）"""
        task = self.data_manager.get_task_by_id(task_id)
        if not task:
            return
        task.status = status
        self.data_manager.save_task(task)

        # 更新任务列表
        self._refresh_task_lists()
        self.updated_at = datetime.now()

    def _refresh_task_lists(self):
        """刷新任务列表（按状态分类）"""
        all_tasks = self.data_manager.get_all_tasks()
        self.pending_tasks = [t for t in all_tasks if t.status == "pending"]
        self.running_tasks = [t for t in all_tasks if t.status == "running"]
        self.completed_tasks = [t for t in all_tasks if t.status == "completed"]