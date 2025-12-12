# 核心类：StateManager（全局状态管理器）
from dataclasses import dataclass, field
from datetime import datetime
from data.data_manager import DataManager
from data.models import TaskStatus, AgentStateModel  # 补充导入枚举和模型
from utils.logger import get_logger  # 补充日志


@dataclass
class StateManager:
    """全局状态管理器：跟踪所有Agent/任务状态，与DataManager深度联动"""
    agents: dict = field(default_factory=dict)  # {agent_id: Agent实例}
    pending_tasks: list = field(default_factory=list)
    running_tasks: list = field(default_factory=list)
    completed_tasks: list = field(default_factory=list)
    failed_tasks: list = field(default_factory=list)  # 新增：失败任务列表
    data_manager: DataManager = field(default_factory=DataManager)
    updated_at: datetime = field(default_factory=datetime.now)
    logger: object = field(default_factory=lambda: get_logger("state_manager"))  # 新增：日志

    def register_agent(self, agent):
        """注册Agent到状态管理器（同步持久化Agent初始状态）"""
        self.agents[agent.agent_id] = agent
        # 同步Agent初始状态到DataManager
        self.sync_agent_state(agent.agent_id)
        self.updated_at = datetime.now()
        self.logger.info(f"Agent {agent.agent_id} 已注册到状态管理器")

    def unregister_agent(self, agent_id: str):
        """注销Agent（同时删除持久化状态）"""
        if agent_id in self.agents:
            # 删除持久化的Agent状态
            self.data_manager.delete_agent_state(agent_id)  # 需给DataManager补充delete方法
            del self.agents[agent_id]
            self.updated_at = datetime.now()
            self.logger.info(f"Agent {agent_id} 已注销")
        else:
            self.logger.warning(f"注销Agent失败：{agent_id} 不存在")

    def get_agent_by_id(self, agent_id: str):
        """新增：高效获取Agent实例（避免遍历）"""
        return self.agents.get(agent_id, None)

    def sync_agent_state(self, agent_id: str):
        """新增：同步Agent状态到DataManager"""
        agent = self.get_agent_by_id(agent_id)
        if not agent:
            self.logger.warning(f"同步Agent状态失败：{agent_id} 不存在")
            return
        # 转换Agent状态为AgentStateModel
        state_model = AgentStateModel(
            agent_id=agent.agent_id,
            agent_type=agent.agent_type,
            status=agent.state.status,
            load=agent.state.load,
            error_msg=agent.state.error_msg,
            updated_at=datetime.now()
        )
        self.data_manager.save_agent_state(state_model)
        self.logger.debug(f"Agent {agent_id} 状态已同步到数据管理器")

    def load_persistent_data(self):
        """新增：加载持久化的Agent/任务状态（系统启动时调用）"""
        # 1. 加载任务状态（刷新任务列表）
        self._refresh_task_lists()
        self.logger.info(
            f"加载持久化任务完成：待执行{len(self.pending_tasks)} | 运行中{len(self.running_tasks)} | 已完成{len(self.completed_tasks)} | 失败{len(self.failed_tasks)}")

        # 2. 加载Agent状态（同步到已注册的Agent实例）
        all_agent_states = self.data_manager.get_all_agent_states()
        for agent_id, state_model in all_agent_states.items():
            agent = self.get_agent_by_id(agent_id)
            if agent:
                # 同步状态到Agent实例
                agent.state.status = state_model.status
                agent.state.load = state_model.load
                agent.state.error_msg = state_model.error_msg
                agent.state.updated_at = state_model.updated_at
                self.logger.debug(f"Agent {agent_id} 持久化状态已加载")
        self.logger.info(f"加载持久化Agent状态完成：共{len(all_agent_states)}个Agent")

    def add_task(self, task):
        """新增：注册新任务（同步到数据管理器）"""
        self.data_manager.save_task(task)
        self._refresh_task_lists()
        self.updated_at = datetime.now()
        self.logger.info(f"任务 {task.task_id} 已注册到状态管理器")

    def remove_task(self, task_id: str):
        """新增：删除任务（同步到数据管理器）"""
        success = self.data_manager.delete_task(task_id)
        if success:
            self._refresh_task_lists()
            self.updated_at = datetime.now()
            self.logger.info(f"任务 {task_id} 已从状态管理器删除")
        else:
            self.logger.warning(f"删除任务失败：{task_id} 不存在")

    def update_task_status(self, task_id: str, status: str):
        """优化：更新任务状态（增加状态校验+日志）"""
        # 校验状态合法性
        if status not in [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.FAILED]:
            self.logger.error(f"更新任务状态失败：非法状态 {status}")
            return

        task = self.data_manager.get_task_by_id(task_id)
        if not task:
            self.logger.warning(f"更新任务状态失败：任务 {task_id} 不存在")
            return

        old_status = task.status
        task.status = status
        self.data_manager.save_task(task)

        # 刷新任务列表
        self._refresh_task_lists()
        self.updated_at = datetime.now()
        self.logger.info(f"任务 {task_id} 状态更新：{old_status} → {status}")

    def _refresh_task_lists(self):
        """优化：刷新任务列表（补充failed状态，使用枚举避免硬编码）"""
        all_tasks = self.data_manager.get_all_tasks()
        self.pending_tasks = [t for t in all_tasks if t.status == TaskStatus.PENDING]
        self.running_tasks = [t for t in all_tasks if t.status == TaskStatus.RUNNING]
        self.completed_tasks = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]
        self.failed_tasks = [t for t in all_tasks if t.status == TaskStatus.FAILED]  # 新增：失败任务