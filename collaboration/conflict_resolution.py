# collaboration/conflict_resolution.py
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from utils.logger import get_logger


class ConflictType(Enum):
    """
    冲突类型枚举
    """
    RESOURCE_CONFLICT = "resource_conflict"  # 资源冲突
    TASK_CONFLICT = "task_conflict"          # 任务冲突
    DATA_CONFLICT = "data_conflict"          # 数据冲突
    AGENT_CONFLICT = "agent_conflict"        # Agent冲突
    PRIORITY_CONFLICT = "priority_conflict"  # 优先级冲突


class ConflictResolutionStrategy(Enum):
    """
    冲突解决策略枚举
    """
    PRIORITY_BASED = "priority_based"        # 基于优先级
    TIMESTAMP_BASED = "timestamp_based"      # 基于时间戳
    AGENT_RANK_BASED = "agent_rank_based"    # 基于Agent等级
    NEGOTIATION_BASED = "negotiation_based"  # 基于协商
    CUSTOM_STRATEGY = "custom_strategy"      # 自定义策略


@dataclass
class Conflict:
    """
    冲突数据模型
    """
    conflict_id: str                         # 冲突唯一标识符
    conflict_type: ConflictType              # 冲突类型
    involved_agents: List[str]               # 涉及的Agent ID列表
    involved_tasks: List[str] = field(default_factory=list)  # 涉及的任务ID列表
    resource: Optional[str] = None           # 冲突资源
    priority: int = 0                        # 冲突优先级：0-低, 1-中, 2-高
    description: str = ""                    # 冲突描述
    created_at: datetime = field(default_factory=datetime.now)
    resolved: bool = False                   # 是否已解决
    resolved_by: Optional[str] = None        # 解决者Agent ID
    resolved_at: Optional[datetime] = None   # 解决时间
    resolution_strategy: Optional[ConflictResolutionStrategy] = None  # 使用的解决策略
    resolution_result: Dict = field(default_factory=dict)  # 解决结果


class ConflictDetector:
    """
    冲突检测器：负责检测系统中的各种冲突
    """
    def __init__(self):
        self.logger = get_logger("conflict_detector")

    def detect_resource_conflict(self, resource: str, agents: Dict[str, object]) -> List[Conflict]:
        """
        检测资源冲突：多个Agent同时请求同一资源
        """
        from uuid import uuid4
        
        # 检查哪些Agent正在使用或请求该资源
        involved_agents = [agent_id for agent_id, agent in agents.items() \
                         if hasattr(agent, 'resources') and resource in agent.resources]
        
        if len(involved_agents) < 2:
            return []
        
        conflict = Conflict(
            conflict_id=str(uuid4()),
            conflict_type=ConflictType.RESOURCE_CONFLICT,
            involved_agents=involved_agents,
            resource=resource,
            description=f"多个Agent同时请求资源：{resource}",
            priority=2  # 资源冲突优先级较高
        )
        
        self.logger.warning(f"检测到资源冲突：{conflict.description}")
        return [conflict]

    def detect_task_conflict(self, tasks: List[object], agents: Dict[str, object]) -> List[Conflict]:
        """
        检测任务冲突：同一Agent被分配了相互冲突的任务
        """
        from uuid import uuid4
        conflicts = []
        
        # 按Agent分组任务
        agent_tasks = {}
        for task in tasks:
            if hasattr(task, 'executor_agent_id') and task.executor_agent_id:
                if task.executor_agent_id not in agent_tasks:
                    agent_tasks[task.executor_agent_id] = []
                agent_tasks[task.executor_agent_id].append(task)
        
        # 检查每个Agent的任务是否冲突
        for agent_id, agent_tasks_list in agent_tasks.items():
            if len(agent_tasks_list) < 2:
                continue
            
            # 简化冲突检测：检查是否有多个高优先级任务
            high_priority_tasks = [task for task in agent_tasks_list \
                                 if hasattr(task, 'priority') and task.priority >= 2]
            
            if len(high_priority_tasks) >= 2:
                conflict = Conflict(
                    conflict_id=str(uuid4()),
                    conflict_type=ConflictType.TASK_CONFLICT,
                    involved_agents=[agent_id],
                    involved_tasks=[task.task_id for task in high_priority_tasks],
                    description=f"Agent {agent_id} 被分配了多个高优先级任务",
                    priority=1
                )
                conflicts.append(conflict)
                self.logger.warning(f"检测到任务冲突：{conflict.description}")
        
        return conflicts

    def detect_data_conflict(self, data_operations: List[Dict]) -> List[Conflict]:
        """
        检测数据冲突：多个Agent同时修改同一数据
        """
        from uuid import uuid4
        conflicts = []
        
        # 按数据项分组操作
        data_operations_map = {}
        for operation in data_operations:
            data_key = operation.get('data_key')
            if not data_key:
                continue
            
            if data_key not in data_operations_map:
                data_operations_map[data_key] = []
            data_operations_map[data_key].append(operation)
        
        # 检查每个数据项的操作是否冲突
        for data_key, operations in data_operations_map.items():
            if len(operations) < 2:
                continue
            
            # 检查是否有多个写操作
            write_operations = [op for op in operations if op.get('operation_type') == 'write']
            if len(write_operations) >= 2:
                involved_agents = list(set(op.get('agent_id') for op in write_operations))
                conflict = Conflict(
                    conflict_id=str(uuid4()),
                    conflict_type=ConflictType.DATA_CONFLICT,
                    involved_agents=involved_agents,
                    resource=data_key,
                    description=f"多个Agent同时修改数据：{data_key}",
                    priority=2
                )
                conflicts.append(conflict)
                self.logger.warning(f"检测到数据冲突：{conflict.description}")
        
        return conflicts

    def detect_all_conflicts(self, state_manager: object) -> List[Conflict]:
        """
        检测所有类型的冲突
        """
        conflicts = []
        
        # 检测任务冲突
        all_tasks = (state_manager.pending_tasks + state_manager.running_tasks + 
                    state_manager.completed_tasks + state_manager.failed_tasks)
        conflicts.extend(self.detect_task_conflict(all_tasks, state_manager.agents))
        
        # 检测资源冲突（示例：假设资源为 "gpu"）
        conflicts.extend(self.detect_resource_conflict("gpu", state_manager.agents))
        
        # 这里可以添加更多冲突检测逻辑
        
        return conflicts


class ConflictResolver:
    """
    冲突解决器：负责解决系统中的各种冲突
    """
    def __init__(self):
        self.logger = get_logger("conflict_resolver")
        self.strategies: Dict[ConflictResolutionStrategy, Callable] = {
            ConflictResolutionStrategy.PRIORITY_BASED: self._resolve_by_priority,
            ConflictResolutionStrategy.TIMESTAMP_BASED: self._resolve_by_timestamp,
            ConflictResolutionStrategy.AGENT_RANK_BASED: self._resolve_by_agent_rank,
            ConflictResolutionStrategy.NEGOTIATION_BASED: self._resolve_by_negotiation
        }

    def _resolve_by_priority(self, conflict: Conflict, context: Dict) -> Dict:
        """
        基于优先级解决冲突
        """
        self.logger.info(f"使用优先级策略解决冲突：{conflict.conflict_id}")
        
        if conflict.conflict_type == ConflictType.TASK_CONFLICT:
            # 优先级高的任务优先执行
            return {
                "strategy": ConflictResolutionStrategy.PRIORITY_BASED.value,
                "decision": "优先执行高优先级任务",
                "affected_agents": conflict.involved_agents
            }
        elif conflict.conflict_type == ConflictType.RESOURCE_CONFLICT:
            # 优先级高的Agent获得资源
            return {
                "strategy": ConflictResolutionStrategy.PRIORITY_BASED.value,
                "decision": "优先级高的Agent获得资源",
                "affected_agents": conflict.involved_agents
            }
        
        return {
            "strategy": ConflictResolutionStrategy.PRIORITY_BASED.value,
            "decision": "默认优先级策略",
            "affected_agents": conflict.involved_agents
        }

    def _resolve_by_timestamp(self, conflict: Conflict, context: Dict) -> Dict:
        """
        基于时间戳解决冲突（先到先得）
        """
        self.logger.info(f"使用时间戳策略解决冲突：{conflict.conflict_id}")
        
        return {
            "strategy": ConflictResolutionStrategy.TIMESTAMP_BASED.value,
            "decision": "先到先得",
            "affected_agents": conflict.involved_agents
        }

    def _resolve_by_agent_rank(self, conflict: Conflict, context: Dict) -> Dict:
        """
        基于Agent等级解决冲突
        """
        self.logger.info(f"使用Agent等级策略解决冲突：{conflict.conflict_id}")
        
        return {
            "strategy": ConflictResolutionStrategy.AGENT_RANK_BASED.value,
            "decision": "等级高的Agent优先",
            "affected_agents": conflict.involved_agents
        }

    def _resolve_by_negotiation(self, conflict: Conflict, context: Dict) -> Dict:
        """
        基于协商解决冲突：让涉及的Agent进行协商
        """
        self.logger.info(f"使用协商策略解决冲突：{conflict.conflict_id}")
        
        return {
            "strategy": ConflictResolutionStrategy.NEGOTIATION_BASED.value,
            "decision": "涉及的Agent进行协商解决",
            "affected_agents": conflict.involved_agents
        }

    def resolve_conflict(self, conflict: Conflict, strategy: ConflictResolutionStrategy, 
                        context: Dict = None, custom_strategy: Optional[Callable] = None) -> Dict:
        """
        解决冲突
        """
        if context is None:
            context = {}
        
        try:
            if strategy == ConflictResolutionStrategy.CUSTOM_STRATEGY and custom_strategy:
                # 使用自定义策略
                result = custom_strategy(conflict, context)
            else:
                # 使用内置策略
                result = self.strategies[strategy](conflict, context)
            
            # 更新冲突状态
            conflict.resolved = True
            conflict.resolved_at = datetime.now()
            conflict.resolution_strategy = strategy
            conflict.resolution_result = result
            
            self.logger.info(f"冲突 {conflict.conflict_id} 已解决，使用策略：{strategy.value}")
            return result
        except Exception as e:
            self.logger.error(f"解决冲突 {conflict.conflict_id} 失败：{e}")
            return {
                "error": str(e),
                "strategy": strategy.value,
                "decision": "解决失败"
            }

    def resolve_all_conflicts(self, conflicts: List[Conflict], 
                            default_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.PRIORITY_BASED) -> List[Dict]:
        """
        解决所有冲突
        """
        results = []
        for conflict in conflicts:
            if not conflict.resolved:
                result = self.resolve_conflict(conflict, default_strategy)
                results.append(result)
        return results


class ConflictResolutionManager:
    """
    冲突解决管理器：整合冲突检测和解决功能
    """
    def __init__(self):
        self.detector = ConflictDetector()
        self.resolver = ConflictResolver()
        self.conflicts: List[Conflict] = []
        self.logger = get_logger("conflict_resolution_manager")

    def detect_conflicts(self, state_manager: object) -> List[Conflict]:
        """
        检测并记录冲突
        """
        new_conflicts = self.detector.detect_all_conflicts(state_manager)
        self.conflicts.extend(new_conflicts)
        return new_conflicts

    def resolve_conflicts(self, strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.PRIORITY_BASED) -> List[Dict]:
        """
        解决所有未解决的冲突
        """
        unresolved_conflicts = [c for c in self.conflicts if not c.resolved]
        results = self.resolver.resolve_all_conflicts(unresolved_conflicts, strategy)
        return results

    def get_conflict_stats(self) -> Dict:
        """
        获取冲突统计信息
        """
        total = len(self.conflicts)
        resolved = len([c for c in self.conflicts if c.resolved])
        unresolved = total - resolved
        
        conflict_type_stats = {}
        for conflict in self.conflicts:
            conflict_type = conflict.conflict_type.value
            if conflict_type not in conflict_type_stats:
                conflict_type_stats[conflict_type] = 0
            conflict_type_stats[conflict_type] += 1
        
        return {
            "total_conflicts": total,
            "resolved_conflicts": resolved,
            "unresolved_conflicts": unresolved,
            "conflicts_by_type": conflict_type_stats
        }

    def get_unresolved_conflicts(self) -> List[Conflict]:
        """
        获取所有未解决的冲突
        """
        return [c for c in self.conflicts if not c.resolved]


# 导出核心类
__all__ = [
    "ConflictType",
    "ConflictResolutionStrategy",
    "Conflict",
    "ConflictDetector",
    "ConflictResolver",
    "ConflictResolutionManager"
]