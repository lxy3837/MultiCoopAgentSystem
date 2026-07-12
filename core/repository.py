"""
Repository 模式 - 异步数据访问层
"""
from typing import Optional, List
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from .models import TaskModel, TaskStatus, AgentStateModel, AgentStatus
from utils.logger import get_logger


class TaskRepository:
    """任务数据仓库"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = get_logger("task_repo")

    async def create(self, task: TaskModel) -> TaskModel:
        """创建任务"""
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        self.logger.info(f"任务已创建: {task.task_id}")
        return task

    async def get_by_id(self, task_id: str) -> Optional[TaskModel]:
        """按 ID 查询"""
        result = await self.session.execute(
            select(TaskModel).where(TaskModel.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, status: Optional[TaskStatus] = None) -> List[TaskModel]:
        """查询所有任务，可按状态筛选"""
        stmt = select(TaskModel)
        if status:
            stmt = stmt.where(TaskModel.status == status)
        stmt = stmt.order_by(TaskModel.create_time.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(self, status: TaskStatus) -> List[TaskModel]:
        """按状态查询"""
        result = await self.session.execute(
            select(TaskModel)
            .where(TaskModel.status == status)
            .order_by(TaskModel.priority.desc(), TaskModel.create_time.asc())
        )
        return list(result.scalars().all())

    async def get_by_executor(self, executor_id: str) -> List[TaskModel]:
        """按执行Agent查询"""
        result = await self.session.execute(
            select(TaskModel).where(TaskModel.executor_agent_id == executor_id)
        )
        return list(result.scalars().all())

    async def update_status(self, task_id: str, status: TaskStatus, **kwargs) -> bool:
        """更新任务状态"""
        task = await self.get_by_id(task_id)
        if not task:
            return False
        task.status = status
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        await self.session.commit()
        self.logger.info(f"任务 {task_id} 状态更新为: {status.value}")
        return True

    async def delete(self, task_id: str) -> bool:
        """删除任务"""
        task = await self.get_by_id(task_id)
        if not task:
            return False
        await self.session.delete(task)
        await self.session.commit()
        self.logger.info(f"任务已删除: {task_id}")
        return True

    async def count_by_status(self, status: TaskStatus) -> int:
        """统计某状态的任务数"""
        result = await self.session.execute(
            select(func.count()).select_from(TaskModel).where(TaskModel.status == status)
        )
        return result.scalar() or 0

    async def get_next_pending(self) -> Optional[TaskModel]:
        """获取下一个待执行任务（按优先级和时间排序）"""
        result = await self.session.execute(
            select(TaskModel)
            .where(TaskModel.status == TaskStatus.PENDING)
            .order_by(TaskModel.priority.desc(), TaskModel.create_time.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class AgentStateRepository:
    """Agent 状态数据仓库"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = get_logger("agent_repo")

    async def save(self, state: AgentStateModel) -> AgentStateModel:
        """保存或更新 Agent 状态"""
        existing = await self.get_by_id(state.agent_id)
        if existing:
            existing.agent_type = state.agent_type
            existing.status = state.status
            existing.load = state.load
            existing.error_msg = state.error_msg
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        else:
            self.session.add(state)
            await self.session.commit()
            await self.session.refresh(state)
            return state

    async def get_by_id(self, agent_id: str) -> Optional[AgentStateModel]:
        """按 ID 查询"""
        result = await self.session.execute(
            select(AgentStateModel).where(AgentStateModel.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> List[AgentStateModel]:
        """查询所有 Agent 状态"""
        result = await self.session.execute(select(AgentStateModel))
        return list(result.scalars().all())

    async def get_by_status(self, status: AgentStatus) -> List[AgentStateModel]:
        """按状态查询"""
        result = await self.session.execute(
            select(AgentStateModel).where(AgentStateModel.status == status)
        )
        return list(result.scalars().all())

    async def update(self, agent_id: str, **kwargs) -> bool:
        """更新 Agent 状态字段"""
        agent = await self.get_by_id(agent_id)
        if not agent:
            return False
        for key, value in kwargs.items():
            if hasattr(agent, key):
                setattr(agent, key, value)
        await self.session.commit()
        return True

    async def delete(self, agent_id: str) -> bool:
        """删除 Agent 状态"""
        agent = await self.get_by_id(agent_id)
        if not agent:
            return False
        await self.session.delete(agent)
        await self.session.commit()
        return True

    async def get_idle_agents_by_type(self, agent_type: str) -> List[AgentStateModel]:
        """获取指定类型且空闲的 Agent"""
        result = await self.session.execute(
            select(AgentStateModel)
            .where(
                AgentStateModel.agent_type == agent_type,
                AgentStateModel.status.in_([AgentStatus.IDLE, AgentStatus.RUNNING]),
            )
            .order_by(AgentStateModel.load.asc())
        )
        return list(result.scalars().all())
