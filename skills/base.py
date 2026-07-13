"""
技能系统基础类定义

定义技能类型、元数据、技能实例、流程节点/边及流程运行器。
参考 KLIP 系统设计，支持 STANDARD（标准）和 FLOW（流程）两种技能类型。
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from utils.logger import get_logger

logger = get_logger("skills")


# ── 技能类型 ──────────────────────────────────────────────────

class SkillType(str, Enum):
    """技能类型枚举

    STANDARD: 标准技能，提供提示词指导 Agent 完成特定任务
    FLOW: 流程技能，定义多步骤的 Agent 工作流
    """
    STANDARD = "standard"
    FLOW = "flow"


# ── 技能元数据 ────────────────────────────────────────────────

class SkillMeta(BaseModel):
    """SKILL.md 文件 Frontmatter 元数据模型

    每个技能目录下的 SKILL.md 文件包含 YAML Frontmatter，
    描述技能的元信息，用于技能发现、匹配和调度。
    """
    name: str = Field(..., description="技能唯一标识名称")
    description: str = Field(..., description="技能功能描述")
    type: SkillType = Field(default=SkillType.STANDARD, description="技能类型")
    tools: list[str] = Field(default_factory=list, description="技能所需的工具列表")
    when_to_use: str = Field(default="", description="触发使用该技能的场景描述")
    agent: str = Field(default="", description="目标 Agent 类型：coordinator / executor / analyzer")


# ── 技能实例 ──────────────────────────────────────────────────

class Skill:
    """已加载的技能实例

    代表一个从 SKILL.md 文件加载的完整技能，
    包含元数据、原始内容和来源信息。
    """

    def __init__(
        self,
        meta: SkillMeta,
        content: str,
        path: Path,
        source: str,
    ):
        """
        Args:
            meta: 技能元数据
            content: SKILL.md 完整内容（含 frontmatter）
            path: SKILL.md 文件路径
            source: 技能来源（builtin / user / project）
        """
        self.meta = meta
        self.content = content
        self.path = path
        self.source = source

    def get_system_prompt(self) -> str:
        """获取格式化的系统提示词

        提取 SKILL.md 中 frontmatter 之后的内容作为系统提示词，
        供 Agent 加载后指导其行为。

        Returns:
            格式化后的系统提示词字符串
        """
        body = self._extract_body()
        return f"[技能: {self.meta.name}]\n{self.meta.description}\n\n{body}"

    def get_flow_diagram(self) -> str | None:
        """提取流程技能中的 Mermaid/D2 流程图

        仅在技能类型为 FLOW 时有效。
        从 SKILL.md 内容中提取 mermaid 或 d2 代码块。

        Returns:
            流程图文本，如果没有流程图则返回 None
        """
        if self.meta.type != SkillType.FLOW:
            return None

        # 尝试提取 mermaid 代码块
        mermaid_match = re.search(
            r'```mermaid\s*\n(.*?)```', self.content, re.DOTALL
        )
        if mermaid_match:
            return mermaid_match.group(1).strip()

        # 尝试提取 d2 代码块
        d2_match = re.search(
            r'```d2\s*\n(.*?)```', self.content, re.DOTALL
        )
        if d2_match:
            return d2_match.group(1).strip()

        return None

    def _extract_body(self) -> str:
        """提取 SKILL.md 中 frontmatter 之后的正文内容

        Returns:
            去除 YAML frontmatter 后的 Markdown 正文
        """
        # 匹配 --- ... --- 之间的 frontmatter
        match = re.match(
            r'^---\s*\n.*?\n---\s*\n', self.content, re.DOTALL
        )
        if match:
            return self.content[match.end():].strip()
        return self.content.strip()

    def __repr__(self) -> str:
        return f"Skill(name={self.meta.name!r}, type={self.meta.type.value}, source={self.source!r})"


# ── 流程定义 ──────────────────────────────────────────────────

class FlowNode(BaseModel):
    """流程节点

    代表 Agent 流程中的一个步骤。

    Attributes:
        id: 节点唯一标识
        type: 节点类型（begin / task / decision / end）
        label: 节点显示标签
        description: 节点详细描述（用于 LLM 理解任务）
    """
    id: str = Field(..., description="节点唯一标识")
    type: str = Field(..., description="节点类型：begin / task / decision / end")
    label: str = Field(..., description="节点显示标签")
    description: str = Field(default="", description="节点详细描述")


class FlowEdge(BaseModel):
    """流程边

    表示流程中节点之间的有向连接。

    Attributes:
        from_id: 起始节点 ID
        to_id: 目标节点 ID
        label: 边的标签（如条件分支的描述）
    """
    from_id: str = Field(..., description="起始节点 ID")
    to_id: str = Field(..., description="目标节点 ID")
    label: str = Field(default="", description="边的标签或条件描述")


class Flow(BaseModel):
    """完整流程定义

    描述一个多步骤 Agent 工作流，由节点和有向边组成。

    Attributes:
        name: 流程名称
        nodes: 流程中的所有节点
        edges: 节点之间的有向边
        start_id: 流程起始节点 ID
        end_id: 流程结束节点 ID
    """
    name: str = Field(default="", description="流程名称")
    nodes: list[FlowNode] = Field(default_factory=list, description="流程节点列表")
    edges: list[FlowEdge] = Field(default_factory=list, description="流程边列表")
    start_id: str = Field(default="", description="起始节点 ID")
    end_id: str = Field(default="", description="结束节点 ID")

    def get_node(self, node_id: str) -> FlowNode | None:
        """根据 ID 获取节点"""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_outgoing_edges(self, node_id: str) -> list[FlowEdge]:
        """获取从指定节点出发的所有边"""
        return [e for e in self.edges if e.from_id == node_id]


# ── 流程运行器 ────────────────────────────────────────────────

class FlowRunner:
    """流程运行器

    负责执行 Flow 定义的 Agent 工作流，
    按步骤遍历节点，处理决策分支和任务执行。
    """

    def __init__(self):
        self._current_node: Optional[str] = None
        self._context: dict[str, Any] = {}

    async def run(self, flow: Flow, context: dict[str, Any]) -> dict[str, Any]:
        """执行流程

        从起始节点开始，按边逐步执行每个节点：
        - begin 节点：初始化上下文
        - task 节点：执行具体任务（依赖外部 LLM/Agent）
        - decision 节点：根据条件选择分支
        - end 节点：返回最终结果

        Args:
            flow: 要执行的流程定义
            context: 初始上下文（可包含已有的数据和配置）

        Returns:
            执行结果上下文

        Raises:
            ValueError: 流程定义不完整或存在死循环
        """
        if not flow.start_id:
            raise ValueError(f"流程 '{flow.name}' 缺少起始节点")

        self._context = dict(context)
        self._current_node = flow.start_id
        visited: set[str] = set()
        max_steps = 100  # 防止死循环

        for _ in range(max_steps):
            if self._current_node in visited:
                logger.warning(f"流程节点 {self._current_node} 重复访问，可能存在循环")
            visited.add(self._current_node)

            node = flow.get_node(self._current_node)
            if node is None:
                raise ValueError(
                    f"流程 '{flow.name}' 中找不到节点 '{self._current_node}'"
                )

            logger.info(f"执行流程节点: {node.id} ({node.type}) - {node.label}")

            if node.type == "begin":
                await self._handle_begin(node)
            elif node.type == "task":
                await self._handle_task(node)
            elif node.type == "decision":
                next_id = await self._handle_decision(node, flow)
                self._current_node = next_id
                continue
            elif node.type == "end":
                await self._handle_end(node)
                return self._context
            else:
                logger.warning(f"未知节点类型: {node.type}")

            # 查找下一个节点
            outgoing = flow.get_outgoing_edges(self._current_node)
            if not outgoing:
                logger.info(f"节点 {self._current_node} 无出边，流程结束")
                return self._context

            # 默认取第一条出边
            self._current_node = outgoing[0].to_id

        raise RuntimeError(
            f"流程 '{flow.name}' 超过最大步骤数 {max_steps}，可能存在死循环"
        )

    async def _handle_begin(self, node: FlowNode) -> None:
        """处理起始节点：初始化上下文"""
        self._context["_flow_started"] = True
        self._context["_current_node"] = node.id
        logger.debug(f"流程起始: {node.label}")

    async def _handle_task(self, node: FlowNode) -> None:
        """处理任务节点

        将任务节点的描述和执行上下文写入 _context，
        供外部 Agent/LLM 读取并实际执行任务。

        子类或外部调用者应读取 _context["_pending_task"] 来获取任务信息，
        并在执行完成后将结果写入 _context["_task_result"]。
        """
        self._context["_pending_task"] = {
            "node_id": node.id,
            "label": node.label,
            "description": node.description,
        }
        logger.info(f"待执行任务: {node.label} - {node.description}")

    async def _handle_decision(self, node: FlowNode, flow: Flow) -> str:
        """处理决策节点

        根据出边的 label 选择下一个节点。
        如果有多条出边，需要外部 LLM 根据上下文做出选择。
        默认情况下：
        - 如果只有一条出边，直接选择
        - 如果出边中包含 "是"/"yes"/"true" 等标签表示条件满足
        - 否则选择第一条出边

        Args:
            node: 决策节点
            flow: 所在流程

        Returns:
            选择的下一个节点 ID
        """
        outgoing = flow.get_outgoing_edges(node.id)
        if not outgoing:
            raise ValueError(f"决策节点 '{node.id}' 缺少出边")

        if len(outgoing) == 1:
            logger.debug(f"决策节点 {node.id}: 唯一路径 -> {outgoing[0].to_id}")
            return outgoing[0].to_id

        # 多条件分支：将决策信息写入上下文，供外部 LLM 选择
        self._context["_pending_decision"] = {
            "node_id": node.id,
            "label": node.label,
            "description": node.description,
            "options": [
                {"edge_label": e.label, "target_id": e.to_id}
                for e in outgoing
            ],
        }

        # 尝试根据上下文中的条件匹配
        condition = self._context.get("_decision_result")
        if condition:
            for edge in outgoing:
                if edge.label.lower() in (
                    condition.lower(),
                    "是", "yes", "true", "pass",
                ):
                    logger.debug(f"决策节点 {node.id}: 条件匹配 '{edge.label}' -> {edge.to_id}")
                    return edge.to_id

        # 默认选择第一条边
        logger.debug(f"决策节点 {node.id}: 默认路径 -> {outgoing[0].to_id}")
        return outgoing[0].to_id

    async def _handle_end(self, node: FlowNode) -> None:
        """处理结束节点"""
        self._context["_flow_completed"] = True
        self._context["_current_node"] = node.id
        logger.info(f"流程结束: {node.label}")

    @property
    def current_node(self) -> str | None:
        """当前执行的节点 ID"""
        return self._current_node

    @property
    def context(self) -> dict[str, Any]:
        """当前执行上下文"""
        return self._context
