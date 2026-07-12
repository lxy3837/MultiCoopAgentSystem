"""
系统主入口 - 使用 Runtime 模式初始化所有组件
参考 kimi-cli 的 KimiCLI.create() 模式
"""
import asyncio
import threading
from dataclasses import dataclass

from config.config import load_config, AppConfig
from core.runtime import Runtime
from core.database import init_db
from core.security import SecurityManager
from utils.logger import init_logger, LogConfig


@dataclass
class SystemContext:
    """全局系统上下文"""
    config: AppConfig
    runtime: Runtime
    initialized: bool = False


_system_context = SystemContext(config=None, runtime=None)
_init_lock = threading.Lock()


async def _setup_agents(runtime: Runtime):
    """创建并注册所有 Agent 到运行时"""
    from agents.specialized_agents.coordinator_agent import CoordinatorAgent
    from agents.specialized_agents.executor_agent import ExecutorAgent
    from agents.specialized_agents.analyzer_agent import AnalyzerAgent

    coordinator = CoordinatorAgent(agent_id="coordinator_001")
    runtime.register_agent(coordinator)

    for i in range(1, 3):
        executor = ExecutorAgent(agent_id=f"executor_{i:03d}")
        runtime.register_agent(executor)

    analyzer = AnalyzerAgent(agent_id="analyzer_001")
    runtime.register_agent(analyzer)

    runtime.logger.info(f"已注册 {len(runtime._agents)} 个 Agent 到运行时")


async def _agent_startup(runtime: Runtime):
    """Agent 启动时注册事件监听"""
    for agent in runtime._agents.values():
        if hasattr(agent, "on_startup"):
            await agent.on_startup()


async def init_agent_system_async() -> SystemContext:
    """异步系统初始化（可在已有事件循环中调用）"""
    global _system_context

    if _system_context.initialized:
        return _system_context

    # 1. 加载配置
    config = load_config()
    _system_context.config = config

    # 2. 初始化日志
    log_cfg = config.log_config
    init_logger(LogConfig(
        level=log_cfg.level, file_path=log_cfg.file_path,
        rotation=log_cfg.rotation, retention=log_cfg.retention,
        json_format=log_cfg.json_format,
    ))

    # 3. 初始化数据库
    await init_db()
    _system_context.runtime = Runtime(config)

    # 4. 初始化安全模块
    sec = SecurityManager()
    sec.init_api_key(config.api_config.api_key)

    # 5. 注册 Agent
    await _setup_agents(_system_context.runtime)

    # 6. 启动运行时
    await _system_context.runtime.start()

    # 7. Agent 启动时注册事件监听
    await _agent_startup(_system_context.runtime)

    _system_context.initialized = True
    return _system_context


def init_agent_system() -> SystemContext:
    """同步入口：初始化 Agent 系统（用于不支持异步的环境中）"""
    if _system_context.initialized:
        return _system_context

    with _init_lock:
        if _system_context.initialized:
            return _system_context

        try:
            # 尝试获取当前运行的事件循环
            loop = asyncio.get_running_loop()
            # 已有事件循环，用 nest_asyncio 或创建任务方式
            raise RuntimeError(
                "检测到正在运行的事件循环，请使用 init_agent_system_async() 替代 init_agent_system()"
            )
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(init_agent_system_async())
                finally:
                    loop.close()
                return result
            raise


def get_agent_context() -> SystemContext:
    """获取系统上下文"""
    if not _system_context.initialized:
        raise RuntimeError("Agent 系统未初始化，请先调用 init_agent_system()")
    return _system_context


async def shutdown_system():
    """优雅停止系统"""
    if _system_context.initialized and _system_context.runtime:
        await _system_context.runtime.stop()
        await _system_context.runtime.db_manager.close()
        _system_context.initialized = False
