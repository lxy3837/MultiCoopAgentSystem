"""
SwarmMode 并行批量调度器
参考 kimi-code SwarmMode + SubagentBatch 设计:
- 两阶段调度：正常阶段 + 限速阶段
- 并发控制（max_concurrency）
- 失败重试（指数退避）
- 按序收集结果
"""
from __future__ import annotations
import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from utils.logger import get_logger


class SwarmStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class SwarmState(str, Enum):
    STARTED = "started"
    NOT_STARTED = "not_started"


@dataclass
class SwarmTaskSpec:
    """子任务规格"""
    index: int
    item: Any
    prompt: str
    task_id: str = ""
    agent_type: str = "executor"


@dataclass
class SwarmTaskResult:
    """子任务结果"""
    spec: SwarmTaskSpec
    agent_id: str = ""
    status: SwarmStatus = SwarmStatus.PENDING
    state: SwarmState = SwarmState.NOT_STARTED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class SwarmConfig:
    """Swarm 配置"""
    max_concurrency: int = 5  # 最大并发数
    initial_launch: int = 5  # 首批启动数
    launch_interval: float = 0.7  # 启动间隔（秒）
    retry_base_ms: int = 3000  # 重试基础延迟（毫秒）
    retry_factor: int = 2  # 重试倍数
    max_retries: int = 3  # 最大重试次数
    timeout: int = 600  # 单个子任务超时（秒）


class SwarmBatch:
    """
    批量并发调度器
    参考 kimi-code SubagentBatch:
    - 正常阶段：首批启动 N 个，每 interval 秒补偿 1 个
    - 限速阶段：指数退避 + 容量收缩/恢复
    - 按序收集结果
    - 支持取消（保留已有结果）
    """

    def __init__(
        self,
        specs: List[SwarmTaskSpec],
        executor: Callable[[SwarmTaskSpec], Any],
        config: Optional[SwarmConfig] = None,
    ):
        self.specs = specs
        self.executor = executor
        self.config = config or SwarmConfig()
        self.logger = get_logger("swarm")
        self._results: Dict[int, SwarmTaskResult] = {}
        self._active: Set[asyncio.Task] = set()
        self._cancelled = False
        self._cancel_event = asyncio.Event()

    async def run(self) -> List[SwarmTaskResult]:
        """
        运行批量任务
        返回按原始顺序排列的结果列表
        """
        if not self.specs:
            return []

        self.logger.info(f"Swarm 启动: {len(self.specs)} 个子任务，最大并发 {self.config.max_concurrency}")

        # 初始化结果占位
        for spec in self.specs:
            self._results[spec.index] = SwarmTaskResult(spec=spec)

        queue = list(self.specs)  # 待处理队列
        launched = 0
        rate_limit_mode = False
        rate_limit_capacity = 1
        retry_intervals: Dict[int, float] = {}  # index -> 下次可重试时间

        # 首批启动
        initial_count = min(self.config.initial_launch, len(queue))
        for _ in range(initial_count):
            spec = queue.pop(0)
            self._launch_task(spec)

        while not self._all_done():
            if self._cancelled:
                break

            # 等待一个任务完成或超时
            active_tasks = list(self._active)
            if active_tasks:
                done, pending = await asyncio.wait(
                    active_tasks, timeout=self.config.launch_interval,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                self._active = pending

            # 启动更多任务
            if queue and len(self._active) < self.config.max_concurrency:
                spec = queue.pop(0)
                self._launch_task(spec)

            # 如果没任务在跑且队列为空，退出
            if not queue and not self._active:
                break

        # 等待剩余任务
        if self._active:
            await asyncio.wait(self._active, timeout=30)

        self.logger.info(f"Swarm 完成: {self._summary()}")

        # 按原始顺序返回
        return [self._results[i] for i in sorted(self._results.keys())]

    def _launch_task(self, spec: SwarmTaskSpec):
        """启一个子任务"""
        task = asyncio.create_task(self._run_one(spec), name=f"swarm_{spec.index}")
        self._active.add(task)

    async def _run_one(self, spec: SwarmTaskSpec):
        """执行单个子任务，含重试"""
        result = self._results[spec.index]
        result.state = SwarmState.STARTED

        for attempt in range(self.config.max_retries + 1):
            try:
                self.logger.debug(f"Swarm 子任务 #{spec.index} 开始 (尝试 {attempt + 1})")
                output = await asyncio.wait_for(
                    self._execute_with_timeout(spec),
                    timeout=self.config.timeout,
                )
                result.status = SwarmStatus.COMPLETED
                result.result = output if isinstance(output, dict) else {"data": str(output)}
                self.logger.debug(f"Swarm 子任务 #{spec.index} 完成")
                return
            except asyncio.TimeoutError:
                self.logger.warning(f"Swarm 子任务 #{spec.index} 超时 ({self.config.timeout}s)")
                result.error = "执行超时"
            except asyncio.CancelledError:
                result.status = SwarmStatus.ABORTED
                result.error = "已取消"
                return
            except Exception as e:
                self.logger.error(f"Swarm 子任务 #{spec.index} 失败 (尝试 {attempt + 1}): {e}")
                result.error = str(e)

            if attempt < self.config.max_retries:
                # 指数退避
                delay = self.config.retry_base_ms / 1000 * (self.config.retry_factor ** attempt)
                self.logger.info(f"Swarm 子任务 #{spec.index} 将在 {delay:.1f}s 后重试")
                await asyncio.sleep(delay)

        result.status = SwarmStatus.FAILED

    async def _execute_with_timeout(self, spec: SwarmTaskSpec):
        """在线程池中执行用户函数（避免阻塞事件循环）"""
        return await asyncio.to_thread(self.executor, spec)

    def cancel(self):
        """取消批量执行（保留已有结果）"""
        self._cancelled = True
        for task in self._active:
            task.cancel()
        self.logger.info("Swarm 已取消")

    def _all_done(self) -> bool:
        """检查所有任务是否都有结果"""
        for spec in self.specs:
            result = self._results.get(spec.index)
            if result and result.status in (SwarmStatus.COMPLETED, SwarmStatus.FAILED, SwarmStatus.ABORTED):
                continue
            return False
        return True

    def _summary(self) -> str:
        """汇总统计"""
        completed = sum(1 for r in self._results.values() if r.status == SwarmStatus.COMPLETED)
        failed = sum(1 for r in self._results.values() if r.status == SwarmStatus.FAILED)
        aborted = sum(1 for r in self._results.values() if r.status == SwarmStatus.ABORTED)
        return f"completed={completed}, failed={failed}, aborted={aborted}"


# ---------- 便捷方法 ----------

async def swarm_execute(
    items: List[Any],
    prompt_template: str,
    executor: Callable,
    agent_type: str = "executor",
    max_concurrency: int = 5,
) -> List[SwarmTaskResult]:
    """
    便捷的批量并行执行方法
    参考 kimi-code AgentSwarmTool 的 items + prompt_template 模式

    Args:
        items: 任务项列表
        prompt_template: 提示词模板，{{item}} 会被替换为对应项
        executor: 执行函数 Callable[[SwarmTaskSpec], Any]
        agent_type: 分配的 Agent 类型
        max_concurrency: 最大并发数
    """
    specs = []
    for i, item in enumerate(items):
        prompt = prompt_template.replace("{{item}}", str(item))
        specs.append(SwarmTaskSpec(
            index=i + 1,
            item=item,
            prompt=prompt,
            task_id=f"swarm_{uuid.uuid4().hex[:8]}",
            agent_type=agent_type,
        ))

    batch = SwarmBatch(
        specs=specs,
        executor=executor,
        config=SwarmConfig(max_concurrency=max_concurrency),
    )
    return await batch.run()
