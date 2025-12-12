# 核心类：GlobalAgentContext（全局Agent上下文，共享实例）
# 核心函数：init_agent_system()（初始化多Agent系统）
from dataclasses import dataclass
from agents.specialized_agents.coordinator_agent import CoordinatorAgent
from collaboration.state_manager import StateManager
from utils.logger import init_logger
from config.config import load_config, AppConfig


@dataclass
class GlobalAgentContext:
    """全局Agent上下文：统一管理核心实例"""
    config: AppConfig
    state_manager: StateManager
    coordinator_agent: CoordinatorAgent
    initialized: bool = False


# 全局上下文单例
_global_context = GlobalAgentContext(config=None, state_manager=None, coordinator_agent=None)


def init_agent_system() -> GlobalAgentContext:
    """初始化多Agent系统（仅执行一次）"""
    if _global_context.initialized:
        return _global_context

    # 1. 加载配置
    config = load_config()
    _global_context.config = config

    # 2. 初始化日志
    init_logger(config.log_config)

    # 3. 初始化状态管理器
    state_manager = StateManager()
    _global_context.state_manager = state_manager

    # 4. 初始化核心Agent
    coordinator = CoordinatorAgent(agent_id="coordinator_001", agent_type="coordinator")
    state_manager.register_agent(coordinator)
    _global_context.coordinator_agent = coordinator

    # 5. 标记初始化完成
    _global_context.initialized = True
    return _global_context


# 对外暴露上下文获取函数
def get_agent_context() -> GlobalAgentContext:
    """获取全局Agent上下文"""
    if not _global_context.initialized:
        raise RuntimeError("Agent系统未初始化，请先调用init_agent_system()")
    return _global_context