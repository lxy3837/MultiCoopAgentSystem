"""
运行时上下文 Runtime - 参考 kimi-cli 的 Runtime 模式
为所有 Agent 提供共享的依赖注入容器
"""
import asyncio
from typing import List, Optional, Dict
from utils.logger import get_logger
from config.config import AppConfig


class Runtime:
    """
    全局运行时上下文
    参考 kimi-cli Runtime 设计：
    - 共享数据库会话工厂
    - 共享事件总线
    - 共享配置
    - Agent 注册表
    - 任务调度器引用
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = get_logger("runtime")
        self._agents: Dict[str, object] = {}  # {agent_id: Agent实例}
        self._event_bus = None  # 延迟初始化
        self._db_manager = None  # 延迟初始化
        self._scheduler = None  # 延迟初始化
        self._lock = asyncio.Lock()
        self._started = False

    # ---------- 懒加载属性 ----------

    @property
    def event_bus(self):
        if self._event_bus is None:
            from core.event_bus import EventBus
            self._event_bus = EventBus()
        return self._event_bus

    @property
    def db_manager(self):
        if self._db_manager is None:
            from core.database import DatabaseManager
            self._db_manager = DatabaseManager()
        return self._db_manager

    @property
    def scheduler(self):
        if self._scheduler is None:
            from core.scheduler import TaskScheduler
            self._scheduler = TaskScheduler(self)
        return self._scheduler

    # ---------- Agent 管理 ----------

    def register_agent(self, agent) -> None:
        """注册 Agent 到运行时"""
        self._agents[agent.agent_id] = agent
        agent.runtime = self  # 注入 Runtime 引用
        self.logger.info(f"Agent {agent.agent_id} ({agent.agent_type}) 已注册到运行时")

    def unregister_agent(self, agent_id: str) -> None:
        """注销 Agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            self.logger.info(f"Agent {agent_id} 已离开运行时")

    def get_agent(self, agent_id: str):
        """获取 Agent 实例"""
        return self._agents.get(agent_id)

    def get_agents_by_type(self, agent_type: str) -> List:
        """按类型获取 Agent"""
        return [a for a in self._agents.values() if a.agent_type == agent_type]

    def get_all_agents(self) -> Dict[str, object]:
        """获取所有 Agent"""
        return self._agents.copy()

    def get_available_executors(self) -> List:
        """获取可用的执行 Agent（idle/running 状态，负载未满）"""
        threshold = self.config.agent_config.default_load_threshold
        return [
            a for a in self._agents.values()
            if a.agent_type == "executor"
            and a.state.status in ["idle", "running"]
            and a.state.load < threshold
        ]

    # ---------- 生命周期 ----------

    async def start(self):
        """启动运行时：启动事件总线和调度器"""
        if self._started:
            return
        await self.event_bus.start()
        await self.scheduler.start()
        self._started = True
        self.logger.info("运行时已启动")

    async def stop(self):
        """停止运行时"""
        if not self._started:
            return
        await self.scheduler.stop()
        await self.event_bus.stop()
        self._started = False
        self.logger.info("运行时已停止")

    async def get_session(self):
        """获取数据库会话"""
        async with self.db_manager.session_factory() as session:
            yield session
