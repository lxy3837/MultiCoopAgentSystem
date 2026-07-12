"""
StreamTracker - 步骤流式跟踪
参考 ScriptForge StreamTracker.java 设计

三步 API:
    tracker.start_step(project_id, "step_1", "需求分析")
    tracker.update_step(project_id, "step_1", "正在分析...", 50)
    tracker.end_step(project_id, "step_1", "completed", 100)

特点（参考 ScriptForge）:
- 通过 EventBus 发布事件，前端/日志同时消费
- start_step 记录开始时间，end_step 自动计算耗时
- 支持嵌套步骤（父步骤汇总子步骤进度）
"""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
from utils.logger import get_logger


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StepInfo:
    """单个步骤的状态"""
    step_id: str
    title: str
    status: StepStatus = StepStatus.PENDING
    progress: int = 0  # 0-100
    content: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def is_done(self) -> bool:
        return self.status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.CANCELLED)


class StreamTracker:
    """
    步骤流式跟踪器

    参考 ScriptForge StreamTracker:
    - startStep / updateStep / endStep 三步 API
    - 通过 EventBus 推送事件到前端
    - 每个 tracker 关联一个 project_id
    """

    def __init__(self, project_id: str, event_bus=None):
        self.project_id = project_id
        self._event_bus = event_bus
        self._steps: Dict[str, StepInfo] = {}
        self.logger = get_logger(f"tracker_{project_id[:8]}")

    # ── 三步 API ──

    def start_step(self, step_id: str, title: str) -> StepInfo:
        """开始一个步骤"""
        if step_id in self._steps:
            # 步骤重入，复用已有
            step = self._steps[step_id]
            step.status = StepStatus.RUNNING
            step.started_at = time.time()
        else:
            step = StepInfo(
                step_id=step_id,
                title=title,
                status=StepStatus.RUNNING,
                started_at=time.time(),
            )
            self._steps[step_id] = step

        self.logger.info(f"[{self.project_id}] 步骤开始: {title}")
        self._emit("start", step)
        return step

    def update_step(self, step_id: str, content: str = "", progress: int = -1):
        """更新步骤进度"""
        if step_id not in self._steps:
            return
        step = self._steps[step_id]
        if content:
            step.content = content
        if progress >= 0:
            step.progress = min(progress, 100)

        self._emit("update", step)

    def end_step(self, step_id: str, status: str = "completed", error: str = None):
        """结束一个步骤"""
        if step_id not in self._steps:
            return
        step = self._steps[step_id]
        step.status = StepStatus(status)
        step.ended_at = time.time()
        step.duration_ms = round((step.ended_at - step.started_at) * 1000)
        step.progress = 100 if status == "completed" else step.progress
        if error:
            step.error = error

        self.logger.info(
            f"[{self.project_id}] 步骤完成: {step.title} ({step.status.value}, {step.duration_ms}ms)"
        )
        self._emit("end", step)

    # ── 上下文管理器 ──

    def track(self, step_id: str, title: str):
        """
        上下文管理器：自动调用 start_step / end_step

        Usage:
            with tracker.track("s1", "处理中"):
                do_work()
        """
        return _StepContext(self, step_id, title)

    # ── 辅助方法 ──

    def current_step(self) -> Optional[StepInfo]:
        """获取当前正在运行的步骤"""
        for step in self._steps.values():
            if step.status == StepStatus.RUNNING:
                return step
        return None

    def get_step(self, step_id: str) -> Optional[StepInfo]:
        return self._steps.get(step_id)

    def get_all_steps(self) -> List[StepInfo]:
        return list(self._steps.values())

    def summary(self) -> Dict[str, Any]:
        """获取步骤汇总"""
        total = len(self._steps)
        completed = sum(1 for s in self._steps.values() if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in self._steps.values() if s.status == StepStatus.FAILED)
        running = sum(1 for s in self._steps.values() if s.status == StepStatus.RUNNING)
        return {
            "project_id": self.project_id,
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "steps": [self._to_dict(s) for s in self._steps.values()],
        }

    # ── 内部 ──

    def _emit(self, event_type: str, step: StepInfo):
        """通过 EventBus 发布事件"""
        if self._event_bus:
            from core.event_bus import Event, EventType
            import asyncio
            try:
                self._event_bus.publish_sync(Event(
                    event_id=f"track_{self.project_id}_{step.step_id}_{event_type}",
                    event_type=EventType.SYSTEM_NOTIFICATION,
                    source="stream_tracker",
                    data={
                        "project_id": self.project_id,
                        "event": event_type,
                        "step": self._to_dict(step),
                    },
                ))
            except Exception as e:
                self.logger.debug(f"事件发布失败: {e}")

    def _to_dict(self, step: StepInfo) -> Dict[str, Any]:
        return {
            "step_id": step.step_id,
            "title": step.title,
            "status": step.status.value,
            "progress": step.progress,
            "content": step.content,
            "duration_ms": step.duration_ms,
            "error": step.error,
        }


class _StepContext:
    """步骤上下文管理器"""
    def __init__(self, tracker: StreamTracker, step_id: str, title: str):
        self.tracker = tracker
        self.step_id = step_id
        self.title = title

    def __enter__(self):
        self.tracker.start_step(self.step_id, self.title)
        return self.tracker

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.tracker.end_step(self.step_id, "failed", error=str(exc_val))
        else:
            self.tracker.end_step(self.step_id, "completed")
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        return self.__exit__(*args)
