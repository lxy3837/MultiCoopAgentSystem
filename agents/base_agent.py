# 核心类：AgentState（数据类）、BaseAgent（抽象基类）
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from data import AgentStateModel, DataManager
from utils.logger import get_logger


@dataclass
class AgentState:
    """Agent状态数据模型"""
    agent_id: str
    agent_type: str
    status: str = "idle"  # idle/running/error/stopped
    load: float = 0.0  # 0.0 ~ 1.0
    error_msg: str = ""
    updated_at: datetime = datetime.now()


class BaseAgent(ABC):
    """Agent抽象基类（定义通用接口）"""

    def __init__(self, agent_id: str, agent_type: str):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.state = AgentState(agent_id=agent_id, agent_type=agent_type)
        self.logger = get_logger(f"agent_{agent_id}")

    def start(self):
        """启动Agent"""
        self.state.status = "idle"
        self.state.error_msg = ""
        self.state.updated_at = datetime.now()
        self.logger.info(f"Agent {self.agent_id} 已启动")

    def stop(self):
        """停止Agent"""
        self.state.status = "stopped"
        self.state.updated_at = datetime.now()
        self.logger.info(f"Agent {self.agent_id} 已停止")

    @abstractmethod
    def send_message(self, target_agent_id: str, message: dict):
        """Agent间发送消息（抽象方法）"""
        pass

    @abstractmethod
    def execute_task(self, task: dict) -> dict:
        """执行任务（抽象方法）"""
        pass

    def update_state(self, **kwargs):
        """更新Agent状态（供UI实时展示）"""
        for k, v in kwargs.items():
            if hasattr(self.state, k):
                setattr(self.state, k, v)
        self.state.updated_at = datetime.now()

    # agents/base_agent.py 中新增 stop() 方法
    def stop(self):
        """停止Agent（修改状态为stopped）"""
        self.state.status = "stopped"
        self.state.load = 0.0
        self.state.updated_at = datetime.now()
        # 同步状态到DataManager
        state_model = AgentStateModel(
            agent_id=self.state.agent_id,
            agent_type=self.state.agent_type,
            status=self.state.status,
            load=self.state.load,
            error_msg=self.state.error_msg,
            updated_at=self.state.updated_at
        )
        DataManager().save_agent_state(state_model)
        self.logger.info(f"Agent {self.agent_id} 已停止")