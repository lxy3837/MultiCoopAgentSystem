# collaboration/task_allocation.py
from typing import Dict, List, Optional
from agents.base_agent import BaseAgent, AgentState
from data.models import TaskModel, TaskStatus
from utils.logger import get_logger
from config import load_config, AppConfig


class TaskAllocator:
    """
    任务分配器：核心负责将任务分配给最优Agent执行
    内置算法：贪心分配（负载最低）、类型匹配分配（Agent类型与任务类型匹配）、兜底分配（默认第一个Agent）
    """

    def __init__(self):
        self.config: AppConfig = load_config()
        self.logger = get_logger("task_allocator")
        # 任务类型与Agent类型的匹配映射（可扩展）
        self.task_agent_mapping = {
            "data_process": ["executor"],  # 数据处理任务 → 执行Agent
            "analysis": ["analyzer"],  # 分析任务 → 分析Agent
            "monitor": ["monitor"],  # 监控任务 → 监控Agent
            "notification": ["coordinator"],  # 通知任务 → 协调Agent
            "default": ["executor"]  # 默认任务类型 → 执行Agent
        }

    def _get_eligible_agents(
            self,
            agents: Dict[str, BaseAgent],
            task_type: str
    ) -> List[BaseAgent]:
        """
        筛选符合条件的Agent（状态正常 + 负载低于阈值 + 类型匹配）
        :param agents: 所有Agent字典 {agent_id: Agent实例}
        :param task_type: 任务类型
        :return: 符合条件的Agent列表
        """
        eligible_agents = []
        # 获取匹配的Agent类型
        match_agent_types = self.task_agent_mapping.get(task_type, self.task_agent_mapping["default"])
        # 负载阈值
        load_threshold = self.config.agent_config.default_load_threshold

        for agent in agents.values():
            # 筛选条件：Agent状态为idle/running（非停止/错误） + 负载低于阈值 + 类型匹配
            if (agent.state.status in ["idle", "running"]
                    and agent.state.load < load_threshold
                    and agent.agent_type in match_agent_types):
                eligible_agents.append(agent)

        if not eligible_agents:
            self.logger.warning(f"无符合条件的Agent（任务类型：{task_type}），将选择状态正常的任意Agent")
            # 兜底：选择所有状态正常的Agent（忽略类型/负载）
            eligible_agents = [a for a in agents.values() if a.state.status in ["idle", "running"]]

        return eligible_agents

    def greedy_allocation(self, task: TaskModel, agents: Dict[str, BaseAgent]) -> str:
        """
        贪心分配算法：选择符合条件的Agent中负载最低的
        :param task: 待分配的任务实例（TaskModel）
        :param agents: 所有Agent字典 {agent_id: Agent实例}
        :return: 选中的Agent ID
        """
        if not agents:
            raise RuntimeError("无可用Agent，无法分配任务")

        # 筛选符合条件的Agent
        eligible_agents = self._get_eligible_agents(agents, task.type)
        if not eligible_agents:
            raise RuntimeError("无状态正常的Agent，无法分配任务")

        # 选择负载最低的Agent（负载相同则选idle状态的）
        eligible_agents.sort(
            key=lambda a: (a.state.load, 0 if a.state.status == "idle" else 1)
        )
        selected_agent = eligible_agents[0]

        # 记录分配日志
        self.logger.info(
            f"任务 {task.task_id}（类型：{task.type}）已分配给Agent {selected_agent.agent_id} "
            f"（当前负载：{selected_agent.state.load:.2f}）"
        )

        # 更新任务执行Agent ID
        task.executor_agent_id = selected_agent.agent_id
        task.status = TaskStatus.RUNNING

        return selected_agent.agent_id

    def type_matching_allocation(self, task: TaskModel, agents: Dict[str, BaseAgent]) -> str:
        """
        类型匹配优先分配算法：优先选择类型完全匹配且状态最优的Agent
        :param task: 待分配的任务实例
        :param agents: 所有Agent字典
        :return: 选中的Agent ID
        """
        if not agents:
            raise RuntimeError("无可用Agent，无法分配任务")

        # 筛选类型完全匹配的Agent
        match_agent_types = self.task_agent_mapping.get(task.type, self.task_agent_mapping["default"])
        type_match_agents = [a for a in agents.values() if
                             a.agent_type in match_agent_types and a.state.status in ["idle", "running"]]

        if type_match_agents:
            # 类型匹配的Agent中选负载最低的
            type_match_agents.sort(key=lambda a: a.state.load)
            selected_agent = type_match_agents[0]
        else:
            # 兜底：使用贪心算法
            selected_agent_id = self.greedy_allocation(task, agents)
            return selected_agent_id

        # 记录日志并更新任务
        self.logger.info(
            f"任务 {task.task_id}（类型：{task.type}）通过类型匹配分配给Agent {selected_agent.agent_id}"
        )
        task.executor_agent_id = selected_agent.agent_id
        task.status = TaskStatus.RUNNING

        return selected_agent.agent_id

    def custom_allocation(self, task: TaskModel, agents: Dict[str, BaseAgent],
                          custom_rule: Optional[callable] = None) -> str:
        """
        自定义分配算法：支持传入自定义规则函数
        :param task: 待分配任务
        :param agents: 所有Agent字典
        :param custom_rule: 自定义规则函数（入参：eligible_agents, task；返回：selected_agent）
        :return: 选中的Agent ID
        """
        eligible_agents = self._get_eligible_agents(agents, task.type)
        if not eligible_agents:
            raise RuntimeError("无可用Agent，无法分配任务")

        if custom_rule and callable(custom_rule):
            selected_agent = custom_rule(eligible_agents, task)
        else:
            # 默认使用贪心算法
            selected_agent = sorted(eligible_agents, key=lambda a: a.state.load)[0]

        self.logger.info(f"任务 {task.task_id} 通过自定义规则分配给Agent {selected_agent.agent_id}")
        task.executor_agent_id = selected_agent.agent_id
        task.status = TaskStatus.RUNNING

        return selected_agent.agent_id


# 导出核心类
__all__ = ["TaskAllocator"]