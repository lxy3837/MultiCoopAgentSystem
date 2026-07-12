"""
SQLAlchemy ORM 模型定义
"""
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, JSON, Integer, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
import enum


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


class TaskModel(Base):
    """任务表"""
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status_enum"), default=TaskStatus.PENDING, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    executor_agent_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    error_msg: Mapped[str] = mapped_column(Text, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=True)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "type": self.type,
            "params": self.params,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "priority": self.priority,
            "executor_agent_id": self.executor_agent_id,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error_msg": self.error_msg,
            "result": self.result,
        }


class AgentStateModel(Base):
    """Agent 状态表"""
    __tablename__ = "agent_states"

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[AgentStatus] = mapped_column(
        SAEnum(AgentStatus, name="agent_status_enum"), default=AgentStatus.IDLE
    )
    load: Mapped[float] = mapped_column(Float, default=0.0)
    error_msg: Mapped[str] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "status": self.status.value if isinstance(self.status, AgentStatus) else self.status,
            "load": self.load,
            "error_msg": self.error_msg,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
