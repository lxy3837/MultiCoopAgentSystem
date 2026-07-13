# agents/specialized_agents/coordinator_agent.py
import json
from agents.base_agent import BaseAgent
from datetime import datetime
from core.event_bus import Event, EventType
from core.models import TaskStatus


class CoordinatorAgent(BaseAgent):
    """
    协调 Agent - 负责任务分配、冲突解决、Agent 调度
    参考 kimi-cli 的 Coordinator + FlowRunner 模式
    """

    def __init__(self, agent_id: str, agent_type: str = "coordinator"):
        super().__init__(agent_id, agent_type)
        self.logger = self.logger

    async def on_startup(self):
        """启动时注册事件监听"""
        # 监听需要协调的事件
        self.event_bus.subscribe(EventType.TASK_CREATED, self._handle_task_created)
        self.event_bus.subscribe(EventType.TASK_FAILED, self._handle_task_failed)
        self.event_bus.subscribe(EventType.CONFLICT_DETECTED, self._handle_conflict)
        self.event_bus.subscribe(EventType.SYSTEM_NOTIFICATION, self._handle_system_event)
        self.logger.info(f"协调 Agent {self.agent_id} 已注册事件监听")

    async def _handle_task_created(self, event: Event):
        """处理任务创建事件：触发调度分配"""
        task_id = event.data.get("task_id")
        self.logger.info(f"协调 Agent 收到任务创建事件: {task_id}")
        # 任务由调度器自动分配，此处可用于额外协调逻辑

    async def _handle_task_failed(self, event: Event):
        """处理任务失败事件：决定是否需要人工干预"""
        task_id = event.data.get("task_id")
        error = event.data.get("error", "")
        self.logger.warning(f"协调 Agent 收到任务失败: {task_id}, 错误: {error}")

        # 发布通知事件，UI 层可以展示
        await self.broadcast(
            "task_failed_alert",
            {"task_id": task_id, "error": error, "requires_intervention": True},
            priority=2,
        )

    async def _handle_conflict(self, event: Event):
        """处理冲突检测事件：执行冲突解决"""
        self.logger.info(f"协调 Agent 处理冲突事件: {event.event_id}")
        await self.resolve_conflicts()

    async def _handle_system_event(self, event: Event):
        """处理系统事件"""
        action = event.data.get("action", "")
        if action == "check_conflicts":
            await self.resolve_conflicts()

    async def execute_task(self, task: dict) -> dict:
        """协调 Agent 本身不执行任务，而是协调分配。
        当 LLM 可用时，使用 AI 智能规划任务分配策略。"""
        self.update_state(status="running", load=0.3)
        try:
            task_id = task.get("task_id", "unknown")
            task_type = task.get("type", "unknown")
            task_name = task.get("name", f"Task-{task_id}")

            self.logger.info(f"协调 Agent 开始分配任务: {task_id} ({task_type})")

            # 1. 冲突检测
            conflicts_detected = await self._check_conflicts()
            if conflicts_detected:
                await self.resolve_conflicts()

            # 2. 使用 LLM 智能规划（如果可用）
            plan = None
            if self.llm_available:
                try:
                    plan = await self._ai_plan_task(task)
                except Exception as e:
                    self.logger.warning(f"LLM 规划失败，使用默认策略: {e}")

            # 3. 分配通知
            await self.broadcast("task_assigning", {
                "task_id": task_id,
                "task_type": task_type,
                "task_name": task_name,
                "coordinator": self.agent_id,
                "ai_plan": plan,
            })

            self.update_state(status="idle", load=0.0)
            return {"code": 0, "msg": f"任务 {task_id} 已进入调度队列", "ai_plan": plan}

        except Exception as e:
            self.update_state(status="error", error_msg=str(e), load=0.0)
            self.logger.error(f"协调 Agent 任务分配失败: {e}")
            return {"code": -1, "msg": str(e)}

    async def _ai_plan_task(self, task: dict) -> dict | None:
        """使用 AI 分析任务并生成分配计划"""
        task_id = task.get("task_id", "unknown")
        task_type = task.get("type", "unknown")
        task_name = task.get("name", "")
        params = task.get("params", {})

        # 获取可用 agent 列表
        agents = self.runtime.get_all_agents()
        agent_list = [
            {"id": aid, "type": a.agent_type, "status": a.state.status, "load": a.state.load}
            for aid, a in agents.items()
        ]

        prompt = f"""你需要为以下任务制定分配策略：

## 任务信息
- 任务ID: {task_id}
- 任务类型: {task_type}  
- 任务名称: {task_name}
- 参数: {json.dumps(params, ensure_ascii=False)}

## 可用 Agent
{json.dumps(agent_list, ensure_ascii=False, indent=2)}

## 要求
分析任务需求，推荐最合适的 Agent 分配方案。考虑：
1. 任务类型与 Agent 类型的匹配度
2. Agent 当前负载状态
3. 是否有历史冲突风险

返回 JSON 格式：
{{"recommended_agent": "agent_id", "reason": "分配理由", "priority": "high|medium|low", "estimated_steps": 预估步骤数}}"""

        result = await self.llm.agent_analyze(
            task_description=prompt,
            skill_prompts=self.get_skill_prompts(),
        )
        # 尝试提取 JSON
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return {"raw_plan": result}

    async def _check_conflicts(self) -> int:
        """检测系统冲突"""
        from collaboration.conflict_resolution import ConflictResolutionManager
        manager = ConflictResolutionManager()

        async with self.db.session_factory() as session:
            from core.repository import AgentStateRepository
            agent_repo = AgentStateRepository(session)
            agent_states = await agent_repo.get_all()

        agents_dict = {s.agent_id: {"load": s.load, "status": s.status.value}
                       for s in agent_states}

        conflicts = manager.detector.detect_resource_conflict("cpu", agents_dict)
        if conflicts:
            for c in conflicts:
                await self.event_bus.publish(Event(
                    event_id=f"evt_conflict_{c.conflict_id}",
                    event_type=EventType.CONFLICT_DETECTED,
                    source=self.agent_id,
                    data={"conflict": c.__dict__ if hasattr(c, '__dict__') else {}},
                    priority=1,
                ))
        return len(conflicts)

    async def resolve_conflicts(self) -> dict:
        """解决系统中存在的冲突"""
        from collaboration.conflict_resolution import ConflictResolutionManager, ConflictResolutionStrategy

        manager = ConflictResolutionManager()
        results = manager.resolve_conflicts(ConflictResolutionStrategy.PRIORITY_BASED)

        for r in results:
            await self.event_bus.publish(Event(
                event_id=f"evt_resolved_{id(r)}",
                event_type=EventType.CONFLICT_RESOLVED,
                source=self.agent_id,
                data=r,
            ))

        return {"resolved_count": len(results)}

    async def assign_task_to_agent(self, task: dict, target_agent_id: str):
        """手动分配任务给指定 Agent"""
        await self.send_message(target_agent_id, {
            "type": "task_assignment",
            "task": task,
            "assigner": self.agent_id,
        })
        self.logger.info(f"任务 {task.get('task_id')} 已手动分配给 {target_agent_id}")


__all__ = ["CoordinatorAgent"]
