# main.py（完整的Agent实例化逻辑）
from dataclasses import dataclass
from agents.base_agent import BaseAgent, AgentState
from agents.specialized_agents.coordinator_agent import CoordinatorAgent
from agents.specialized_agents.executor_agent import ExecutorAgent  # 新增
from agents.specialized_agents.analyzer_agent import AnalyzerAgent  # 新增
from collaboration.state_manager import StateManager
from utils.logger import init_logger
from config import load_config, AppConfig


@dataclass
class GlobalAgentContext:
    config: AppConfig
    state_manager: StateManager
    coordinator_agent: CoordinatorAgent
    initialized: bool = False


_global_context = GlobalAgentContext(config=None, state_manager=None, coordinator_agent=None)


def init_agent_system() -> GlobalAgentContext:
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

    # 4. 创建核心Agent实例（关键：之前只创建了CoordinatorAgent）
    # 4.1 协调Agent（必选）
    coordinator = CoordinatorAgent(agent_id="coordinator_001")
    state_manager.register_agent(coordinator)
    _global_context.coordinator_agent = coordinator

    # 4.2 执行Agent（新增：实际处理任务的Agent）
    executor_001 = ExecutorAgent(agent_id="executor_001")
    executor_002 = ExecutorAgent(agent_id="executor_002")
    state_manager.register_agent(executor_001)
    state_manager.register_agent(executor_002)

    # 4.3 分析Agent（新增：处理分析类任务）
    analyzer_001 = AnalyzerAgent(agent_id="analyzer_001")
    state_manager.register_agent(analyzer_001)

    # 5. 自动启动所有Agent（根据配置）
    if config.agent_config.auto_start:
        for agent in state_manager.agents.values():
            agent.start()  # 调用BaseAgent的start()方法

    # 6. 标记初始化完成
    _global_context.initialized = True
    return _global_context


def get_agent_context() -> GlobalAgentContext:
    if not _global_context.initialized:
        raise RuntimeError("Agent系统未初始化，请先调用init_agent_system()")
    return _global_context