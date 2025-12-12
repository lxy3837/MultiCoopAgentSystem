# 核心类：CoordinatorAgent（继承BaseAgent）
from agents.base_agent import BaseAgent, AgentState
from collaboration.task_allocation import TaskAllocator
from utils.logger import get_logger


class CoordinatorAgent(BaseAgent):
    """协调Agent：负责任务分配、冲突解决、Agent调度"""

    def __init__(self, agent_id: str, agent_type: str = "coordinator"):
        super().__init__(agent_id, agent_type)
        self.task_allocator = TaskAllocator()  # 任务分配器实例
        self.logger = get_logger(f"coordinator_{agent_id}")

    def send_message(self, target_agent_id: str, message: dict):
        """实现消息发送逻辑（简化版）"""
        self.logger.info(f"协调Agent {self.agent_id} 向 {target_agent_id} 发送消息：{message}")
        # 实际场景：对接消息队列/WebSocket
        pass

    def execute_task(self, task: dict) -> dict:
        """协调Agent不执行具体任务，仅分配任务"""
        self.update_state(status="running", load=0.5)
        try:
            # 分配任务给最优ExecutorAgent
            target_agent_id = self.task_allocator.greedy_allocation(
                task=task,
                agents=self.state_manager.agents  # 从状态管理器获取所有Agent
            )
            # 发送任务消息给目标Agent
            self.send_message(target_agent_id, {"type": "task_assignment", "task": task})
            self.update_state(status="idle", load=0.0)
            return {"code": 0, "msg": f"任务已分配给Agent {target_agent_id}"}
        except Exception as e:
            self.update_state(status="error", error_msg=str(e), load=0.0)
            self.logger.error(f"任务分配失败：{e}")
            return {"code": -1, "msg": str(e)}

    def assign_task(self, task):
        """封装任务分配逻辑（供UI调用）"""
        self.execute_task(task.model_dump())