"""
RetryTemplate - 泛型重试框架
参考 ScriptForge RetryTemplate.java 设计

特点（参考 ScriptForge）:
- 默认重试 3 次，间隔 1s/3s/5s 递增
- Callable 模式（同步 + 异步）
- 失败回调 on_failure
- 最终失败抛出 RetryExhaustedError
"""
from __future__ import annotations
import asyncio
import time
import functools
from typing import Any, Callable, Optional, TypeVar
from utils.logger import get_logger

T = TypeVar("T")

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAYS = [1.0, 3.0, 5.0]  # 秒


class RetryExhaustedError(Exception):
    """重试耗尽异常（参考 ScriptForge BusinessException(AGENT_EXECUTION_FAILED)）"""
    def __init__(self, task_name: str, attempts: int, last_error: Optional[Exception] = None):
        self.task_name = task_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"{task_name} - 已达最大重试次数({attempts}次): {last_error}")


class RetryTemplate:
    """
    泛型重试模板

    参考 ScriptForge RetryTemplate:
    - execute(task, name) 同步重试
    - execute_async(task, name) 异步重试
    - 支持自定义重试次数和间隔
    - 失败回调 on_failure
    """

    logger = get_logger("retry")

    @staticmethod
    def execute(
        task: Callable[[], T],
        task_name: str = "task",
        max_retries: int = DEFAULT_MAX_RETRIES,
        delays: list = None,
        on_failure: Optional[Callable[[Exception], None]] = None,
    ) -> T:
        """
        同步重试执行

        Args:
            task: 可调用任务
            task_name: 任务名称（日志用）
            max_retries: 最大重试次数
            delays: 每次重试的等待时间列表
            on_failure: 每次失败时的回调
        """
        if delays is None:
            delays = DEFAULT_RETRY_DELAYS

        actual_retries = min(max_retries, len(delays))
        last_error = None

        for attempt in range(actual_retries + 1):
            try:
                if attempt > 0:
                    RetryTemplate.logger.info(f"{task_name} - 第{attempt}次重试")
                result = task()
                if attempt > 0:
                    RetryTemplate.logger.info(f"{task_name} - 重试成功")
                return result
            except RetryExhaustedError:
                raise
            except Exception as e:
                last_error = e
                if on_failure:
                    on_failure(e)

                if attempt < actual_retries:
                    delay = delays[attempt]
                    RetryTemplate.logger.warning(
                        f"{task_name} - 执行失败，将在{delay:.1f}s后进行第{attempt + 1}次重试: {e}"
                    )
                    time.sleep(delay)

        raise RetryExhaustedError(task_name, actual_retries, last_error)

    @staticmethod
    async def execute_async(
        task: Callable[..., Any],
        task_name: str = "task",
        max_retries: int = DEFAULT_MAX_RETRIES,
        delays: list = None,
        on_failure: Optional[Callable[[Exception], Any]] = None,
    ) -> T:
        """
        异步重试执行

        Args:
            task: 异步可调用任务（sync 函数会被在线程池中执行）
            task_name: 任务名称
            max_retries: 最大重试次数
            delays: 重试间隔
            on_failure: 失败回调（支持 sync/async）
        """
        if delays is None:
            delays = DEFAULT_RETRY_DELAYS

        actual_retries = min(max_retries, len(delays))
        last_error = None

        for attempt in range(actual_retries + 1):
            try:
                if attempt > 0:
                    RetryTemplate.logger.info(f"{task_name} - 第{attempt}次重试")
                if asyncio.iscoroutinefunction(task):
                    result = await task()
                else:
                    result = await asyncio.to_thread(task)
                if attempt > 0:
                    RetryTemplate.logger.info(f"{task_name} - 重试成功")
                return result
            except RetryExhaustedError:
                raise
            except Exception as e:
                last_error = e
                if on_failure:
                    result = on_failure(e)
                    if asyncio.iscoroutine(result):
                        await result

                if attempt < actual_retries:
                    delay = delays[attempt]
                    RetryTemplate.logger.warning(
                        f"{task_name} - 执行失败，将在{delay:.1f}s后进行第{attempt + 1}次重试: {e}"
                    )
                    await asyncio.sleep(delay)

        raise RetryExhaustedError(task_name, actual_retries, last_error)


# ── 装饰器方式 ──

def retry(max_retries: int = DEFAULT_MAX_RETRIES, delays: list = None, task_name: str = None):
    """同步重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            name = task_name or func.__name__
            return RetryTemplate.execute(
                lambda: func(*args, **kwargs),
                task_name=name,
                max_retries=max_retries,
                delays=delays,
            )
        return wrapper
    return decorator


def retry_async(max_retries: int = DEFAULT_MAX_RETRIES, delays: list = None, task_name: str = None):
    """异步重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            name = task_name or func.__name__
            return await RetryTemplate.execute_async(
                lambda: func(*args, **kwargs),
                task_name=name,
                max_retries=max_retries,
                delays=delays,
            )
        return wrapper
    return decorator
