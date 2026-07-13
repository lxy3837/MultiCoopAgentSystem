"""
MCASys Skills 技能系统

提供技能的发现、加载、管理和流程编排功能。

核心组件:
    - SkillType: 技能类型枚举（STANDARD / FLOW）
    - SkillMeta: SKILL.md 元数据模型
    - Skill: 已加载的技能实例
    - SkillManager: 技能发现与生命周期管理
    - Flow / FlowNode / FlowEdge / FlowRunner: 流程编排
    - parse_mermaid / parse_d2: 流程图解析
"""
from skills.base import (
    SkillType,
    SkillMeta,
    Skill,
    FlowNode,
    FlowEdge,
    Flow,
    FlowRunner,
)
from skills.manager import SkillManager
from skills.flow import parse_mermaid, parse_d2

__all__ = [
    # 枚举
    "SkillType",
    # 数据模型
    "SkillMeta",
    # 技能
    "Skill",
    # 流程
    "FlowNode",
    "FlowEdge",
    "Flow",
    "FlowRunner",
    # 管理器
    "SkillManager",
    # 解析器
    "parse_mermaid",
    "parse_d2",
]
