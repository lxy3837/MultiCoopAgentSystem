"""
发布/订阅事件总线 - 参考 kimi-cli 的 RootWireHub 模式
实现 Agent 间异步事件驱动通信
"""
import asyncio
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from utils.logger import get_logger


class EventType(str, Enum):
    """事件类型枚举"""
    TASK_CREATED = "task_created"
    TASK_ASSIGNED = "task_assigned"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRY = "task_retry"
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    AGENT_ERROR = "agent_error"
    AGENT_HEARTBEAT = "agent_heartbeat"
    CONFLICT_DETECTED = "conflict_detected"
    CONFLICT_RESOLVED = "conflict_resolved"
    MESSAGE_RECEIVED = "message_received"
    SYSTEM_NOTIFICATION = "system_notification"


@dataclass
class Event:
    """事件数据模型"""
    event_id: str
    event_type: EventType
    source: str  # 事件来源 Agent ID
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = 0  # 0=普通, 1=重要, 2=紧急


class EventBus:
    """
    发布/订阅事件总线
    参考 kimi-cli RootWireHub 设计：
    - 支持多订阅者模式
    - 异步事件分发
    - 事件历史追踪
    """

    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._wildcard_subscribers: List[Callable] = []  # 监听所有事件的订阅者
        self._queue: asyncio.Queue = asyncio.Queue()
        self._history: List[Event] = []
        self._max_history = 1000
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.logger = get_logger("event_bus")

    def subscribe(self, event_type: EventType, callback: Callable):
        """订阅特定事件类型"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        self.logger.debug(f"已订阅事件: {event_type.value}")

    def subscribe_all(self, callback: Callable):
        """订阅所有事件"""
        self._wildcard_subscribers.append(callback)

    def unsubscribe_all(self, callback: Callable):
        """取消订阅所有事件"""
        if callback in self._wildcard_subscribers:
            self._wildcard_subscribers.remove(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable):
        """取消订阅"""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(callback)

    async def publish(self, event: Event):
        """发布事件（异步）"""
        await self._queue.put(event)
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def publish_sync(self, event: Event):
        """同步发布事件（用于非异步上下文）"""
        self._queue.put_nowait(event)
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    async def _dispatch_loop(self):
        """事件分发循环"""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"事件分发异常: {e}")

    async def _dispatch(self, event: Event):
        """分发单个事件给所有订阅者"""
        # 通知特定类型订阅者
        if event.event_type in self._subscribers:
            for callback in self._subscribers[event.event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    self.logger.error(f"事件回调异常 [{event.event_type.value}]: {e}")

        # 通知通配符订阅者
        for callback in self._wildcard_subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                self.logger.error(f"通配符回调异常: {e}")

    async def start(self):
        """启动事件总线"""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._dispatch_loop())
            self.logger.info("事件总线已启动")

    async def stop(self):
        """停止事件总线"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.logger.info("事件总线已停止")

    def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """获取事件历史"""
        if event_type:
            return [e for e in self._history if e.event_type == event_type][-limit:]
        return self._history[-limit:]

    @property
    def subscriber_count(self) -> int:
        """获取订阅者总数"""
        total = len(self._wildcard_subscribers)
        for subs in self._subscribers.values():
            total += len(subs)
        return total
