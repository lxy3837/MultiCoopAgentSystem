"""协作模块 - 包含Agent间通信、状态管理、冲突解决和任务分配功能"""

from .communication import Message, MessageQueue, CommunicationManager
from .state_manager import StateManager
from .task_allocation import TaskAllocator
from .conflict_resolution import (
    ConflictType,
    ConflictResolutionStrategy,
    Conflict,
    ConflictDetector,
    ConflictResolver,
    ConflictResolutionManager
)

__all__ = [
    # 通信相关
    "Message",
    "MessageQueue",
    "CommunicationManager",
    
    # 状态管理
    "StateManager",
    
    # 任务分配
    "TaskAllocator",
    
    # 冲突解决
    "ConflictType",
    "ConflictResolutionStrategy",
    "Conflict",
    "ConflictDetector",
    "ConflictResolver",
    "ConflictResolutionManager"
]
