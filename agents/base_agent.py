# agents/base_agent.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional
from utils.logger import get_logger


@dataclass
class AgentState:
    """Agent 状态数据类"""
    agent_id: str
    agent_type: str
    status: str = "idle"  # idle / running / error / stopped
    load: float = 0.0
    error_msg: str = ""
    updated_at: datetime = datetime.now()


class BaseAgent(ABC):
    """Agent 抽象基类 - 通过 Runtime 共享依赖注入"""

    def __init__(self, agent_id: str, agent_type: str):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.state = AgentState(agent_id=agent_id, agent_type=agent_type)
        self.logger = get_logger(f"agent_{agent_id}")
        self.runtime: Optional[object] = None  # 由 Runtime.register_agent() 注入
        self._skills: list = []  # Agent 加载的技能列表

    @property
    def event_bus(self):
        """便捷访问事件总线"""
        if self.runtime is None:
            raise RuntimeError(f"Agent {self.agent_id} 未注册到 Runtime")
        return self.runtime.event_bus

    @property
    def db(self):
        """便捷访问数据库管理器"""
        if self.runtime is None:
            raise RuntimeError(f"Agent {self.agent_id} 未注册到 Runtime")
        return self.runtime.db_manager

    @property
    def llm(self):
        """便捷访问 LLM 客户端"""
        if self.runtime is None:
            raise RuntimeError(f"Agent {self.agent_id} 未注册到 Runtime")
        return self.runtime.llm

    @property
    def llm_available(self) -> bool:
        """LLM 是否可用"""
        if self.runtime is None:
            return False
        return self.runtime.llm_available

    @property
    def skills(self) -> list:
        """获取 Agent 已加载的技能列表"""
        return self._skills

    def load_skills(self, skill_names: list[str] | None = None):
        """加载技能到 Agent

        从全局 SkillManager 中加载匹配此 Agent 类型的技能。
        如果指定了 skill_names，则只加载指定的技能。

        Args:
            skill_names: 要加载的技能名称列表，None 表示加载所有匹配的技能
        """
        try:
            from skills import SkillManager
            manager = SkillManager()
            agent_skills = manager.list_skills_by_agent(self.agent_type)
            if skill_names:
                agent_skills = [s for s in agent_skills if s.name in skill_names]
            for skill_meta in agent_skills:
                skill = manager.get_skill(skill_meta.name)
                if skill and skill not in self._skills:
                    self._skills.append(skill)
            self.logger.info(
                f"Agent {self.agent_id} 已加载 {len(self._skills)} 个技能: "
                f"{[s.meta.name for s in self._skills]}"
            )
        except Exception as e:
            self.logger.warning(f"Agent {self.agent_id} 加载技能失败: {e}")

    def get_skill_prompts(self) -> str:
        """获取所有已加载技能的系统提示词合并文本

        Returns:
            合并后的技能提示词，供 LLM 作为系统提示使用
        """
        if not self._skills:
            return ""
        prompts = []
        for skill in self._skills:
            prompts.append(skill.get_system_prompt())
        return "\n\n---\n\n".join(prompts)

    def start(self):
        """启动 Agent"""
        self.state.status = "idle"
        self.state.error_msg = ""
        self.state.updated_at = datetime.now()
        self.logger.info(f"Agent {self.agent_id} ({self.agent_type}) 已启动")

    def stop(self):
        """停止 Agent"""
        self.state.status = "stopped"
        self.state.load = 0.0
        self.state.updated_at = datetime.now()
        self.logger.info(f"Agent {self.agent_id} 已停止")

    async def send_message(self, target_agent_id: str, message: Dict[str, Any]):
        """
        通过事件总线发送消息给目标 Agent
        参考 kimi-cli 的 RootWireHub 发布/订阅模式
        """
        from core.event_bus import Event, EventType
        import uuid

        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.MESSAGE_RECEIVED,
            source=self.agent_id,
            data={
                "target": target_agent_id,
                "message": message,
            },
        )
        await self.event_bus.publish(event)
        self.logger.debug(f"消息已发送: {self.agent_id} -> {target_agent_id}")

    async def broadcast(self, message_type: str, content: Dict[str, Any], priority: int = 0):
        """广播消息给所有 Agent"""
        from core.event_bus import Event, EventType
        import uuid

        await self.event_bus.publish(Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_NOTIFICATION,
            source=self.agent_id,
            data={
                "broadcast": True,
                "message_type": message_type,
                "content": content,
            },
            priority=priority,
        ))

    @abstractmethod
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务（子类实现具体业务逻辑）"""
        pass

    def update_state(self, **kwargs):
        """批量更新 Agent 状态"""
        for k, v in kwargs.items():
            if hasattr(self.state, k):
                setattr(self.state, k, v)
        self.state.updated_at = datetime.now()

    async def persist_state(self):
        """同步 Agent 状态到数据库"""
        from core.models import AgentStateModel, AgentStatus

        async with self.db.session_factory() as session:
            from core.repository import AgentStateRepository
            repo = AgentStateRepository(session)
            await repo.save(AgentStateModel(
                agent_id=self.agent_id,
                agent_type=self.agent_type,
                status=AgentStatus(self.state.status),
                load=self.state.load,
                error_msg=self.state.error_msg,
                updated_at=self.state.updated_at,
            ))

    async def handle_event(self, event):
        """
        处理事件总线消息（子类可重写）
        参考 kimi-cli Agent 的消息处理模式
        """
        # 默认忽略不是发给自己的消息
        target = event.data.get("target", "")
        if target and target != self.agent_id and target != "broadcast":
            return
        self.logger.debug(f"收到事件: {event.event_type.value} from {event.source}")
