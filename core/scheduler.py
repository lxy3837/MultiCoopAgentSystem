"""
后台任务调度器 - 参考 kimi-cli 的 Agent Loop + FlowRunner 模式
实现异步任务调度循环，持续从 PENDING 队列取任务并分配执行
"""
import asyncio
from datetime import datetime
from typing import Optional
from utils.logger import get_logger
from core.event_bus import Event, EventType
from core.repository import TaskRepository, AgentStateRepository
from core.models import TaskStatus, AgentStatus


class TaskScheduler:
    """
    后台任务调度器
    - 持续轮询 PENDING 任务
    - 调用分配算法选择最优 Agent
    - 发送任务到目标 Agent 执行
    - 处理失败重试
    - 支持优雅停止
    """

    def __init__(self, runtime):
        self.runtime = runtime
        self.logger = get_logger("scheduler")
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval = 1.0  # 轮询间隔（秒）
        self._conflict_check_interval = 10  # 冲突检测间隔（秒）
        self._conflict_counter = 0

        # 任务类型 → Agent 类型映射
        self.task_agent_mapping = {
            "data_process": "executor",
            "analysis": "analyzer",
            "monitor": "monitor",
            "notification": "coordinator",
        }

    async def start(self):
        """启动调度循环"""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._schedule_loop())
            self.logger.info("任务调度器已启动")

    async def stop(self):
        """停止调度循环"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.logger.info("任务调度器已停止")

    async def _schedule_loop(self):
        """主调度循环"""
        while self._running:
            try:
                async with self.runtime.db_manager.session_factory() as session:
                    task_repo = TaskRepository(session)
                    agent_repo = AgentStateRepository(session)

                    # 1. 获取下一个待执行任务
                    pending_task = await task_repo.get_next_pending()
                    if pending_task:
                        await self._assign_task(pending_task, task_repo, agent_repo)
                        continue

                # 2. 定期冲突检测
                self._conflict_counter += 1
                if self._conflict_counter >= self._conflict_check_interval:
                    self._conflict_counter = 0
                    await self._check_conflicts()

                # 3. 等待下一次轮询
                await asyncio.sleep(self._poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"调度循环异常: {e}")
                await asyncio.sleep(self._poll_interval)

    async def _assign_task(self, task, task_repo: TaskRepository, agent_repo: AgentStateRepository):
        """
        分配任务给最优 Agent
        参考 kimi-cli 的 TaskAllocator 算法：
        1. 类型匹配优先
        2. 负载最低优先
        """
        target_type = self.task_agent_mapping.get(task.type, "executor")

        # 获取该类型的可用 Agent 状态
        candidate_states = await agent_repo.get_idle_agents_by_type(target_type)

        # 如果指定类型无可用的，用 executor 作为兜底
        if not candidate_states and target_type != "executor":
            candidate_states = await agent_repo.get_idle_agents_by_type("executor")

        if not candidate_states:
            # 无可用的 Agent，任务保持 PENDING（降级为 debug 避免日志洪水）
            self.logger.debug(f"无可用 Agent 执行任务 {task.task_id}（类型：{task.type}）")
            return

        # 选负载最低的
        selected = min(candidate_states, key=lambda a: a.load)
        agent = self.runtime.get_agent(selected.agent_id)

        if not agent:
            self.logger.warning(f"Agent {selected.agent_id} 不在运行时注册表中")
            return

        # 分配并执行
        try:
            task.executor_agent_id = selected.agent_id
            await task_repo.update_status(
                task.task_id, TaskStatus.RUNNING,
                executor_agent_id=selected.agent_id,
                start_time=datetime.now()
            )

            self.logger.info(
                f"任务 {task.task_id}（{task.type}）已分配给 Agent {selected.agent_id}"
            )

            # 发布事件
            await self.runtime.event_bus.publish(Event(
                event_id=f"evt_{task.task_id}_assigned",
                event_type=EventType.TASK_ASSIGNED,
                source="scheduler",
                data={"task_id": task.task_id, "agent_id": selected.agent_id},
            ))

            # 执行任务
            if asyncio.iscoroutinefunction(agent.execute_task):
                result = await agent.execute_task(task.to_dict())
            else:
                result = await asyncio.to_thread(agent.execute_task, task.to_dict())

            # 处理结果
            if result.get("code") == 0:
                await task_repo.update_status(
                    task.task_id, TaskStatus.COMPLETED,
                    end_time=datetime.now(),
                    result=result,
                )
                await self.runtime.event_bus.publish(Event(
                    event_id=f"evt_{task.task_id}_done",
                    event_type=EventType.TASK_COMPLETED,
                    source=selected.agent_id,
                    data={"task_id": task.task_id, "result": result},
                ))
            else:
                await self._handle_task_failure(task, result, task_repo, selected.agent_id)

        except Exception as e:
            self.logger.error(f"任务 {task.task_id} 执行异常: {e}")
            await self._handle_task_failure(
                task, {"code": -1, "msg": str(e)}, task_repo, selected.agent_id
            )

    async def _handle_task_failure(self, task, result: dict, task_repo: TaskRepository, agent_id: str):
        """处理任务失败：重试或标记为失败"""
        task = await task_repo.get_by_id(task.task_id)
        if not task:
            return

        can_retry = task.retry_count < task.max_retries
        if can_retry:
            # 重试
            await task_repo.update_status(
                task.task_id, TaskStatus.PENDING,
                retry_count=task.retry_count + 1,
                error_msg=result.get("msg", ""),
            )
            self.logger.info(
                f"任务 {task.task_id} 将重试（{task.retry_count + 1}/{task.max_retries}）"
            )
            await self.runtime.event_bus.publish(Event(
                event_id=f"evt_{task.task_id}_retry",
                event_type=EventType.TASK_RETRY,
                source=agent_id,
                data={"task_id": task.task_id, "retry": task.retry_count + 1},
            ))
        else:
            # 最终失败
            await task_repo.update_status(
                task.task_id, TaskStatus.FAILED,
                end_time=datetime.now(),
                error_msg=f"重试{task.max_retries}次后仍失败: {result.get('msg', '')}",
            )
            self.logger.error(f"任务 {task.task_id} 最终失败（重试{task.max_retries}次）")
            await self.runtime.event_bus.publish(Event(
                event_id=f"evt_{task.task_id}_failed",
                event_type=EventType.TASK_FAILED,
                source=agent_id,
                data={"task_id": task.task_id, "error": result.get("msg", "")},
            ))

    async def _check_conflicts(self):
        """定期冲突检测（简化版，实际逻辑由 conflict_resolution 模块负责）"""
        self.logger.debug("执行定期冲突检测...")
        # 发布冲突检测事件，由冲突解决模块订阅处理
        await self.runtime.event_bus.publish(Event(
            event_id="evt_scheduled_conflict_check",
            event_type=EventType.SYSTEM_NOTIFICATION,
            source="scheduler",
            data={"action": "check_conflicts"},
        ))
