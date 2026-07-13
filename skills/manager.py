r"""
技能管理器模块

实现分层合并策略的技能发现、加载和缓存管理。
参考 KLIP-8 分层覆盖策略：

1. Builtin 技能（e:\MCASys\skills\builtin\） — 最低优先级，系统内置
2. User 技能（~\.mcasys\skills\） — 中等优先级，用户级自定义
3. Project 技能（.mcasys\skills\） — 最高优先级，项目级覆盖

同名技能按优先级覆盖：project > user > builtin
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import yaml

from skills.base import Skill, SkillMeta, SkillType
from utils.logger import get_logger

logger = get_logger("skills.manager")


class SkillManager:
    """技能管理器

    负责技能的发现、加载、缓存和查询。
    采用分层合并策略，支持同名技能的多级覆盖。
    """

    def __init__(self):
        """初始化技能管理器

        自动检测技能目录路径：
        - builtin: <package>/skills/builtin/
        - user: ~/.mcasys/skills/
        - project: <cwd>/.mcasys/skills/
        """
        self._skills: dict[str, Skill] = {}
        self._cache: dict[str, SkillMeta] = {}

        # Builtin 技能目录（相对于当前文件）
        self._builtin_dir = Path(__file__).resolve().parent / "builtin"

        # User 技能目录
        self._user_dir = Path.home() / ".mcasys" / "skills"

        # Project 技能目录（相对于当前工作目录）
        self._project_dir = Path.cwd() / ".mcasys" / "skills"

    # ── 公共 API ───────────────────────────────────────────────

    def discover_skills(self) -> dict[str, Skill]:
        """扫描所有技能目录并加载 SKILL.md 文件

        按优先级顺序加载，高层覆盖底层：
        1. 先加载 builtin 技能
        2. 再加载 user 技能（覆盖同名）
        3. 最后加载 project 技能（覆盖同名）

        Returns:
            已加载的所有技能字典，key 为技能名
        """
        self._skills.clear()

        # 按优先级从低到高加载（后者覆盖前者）
        layers: list[tuple[str, Path]] = [
            ("builtin", self._builtin_dir),
            ("user", self._user_dir),
            ("project", self._project_dir),
        ]

        for source, directory in layers:
            if not directory.exists():
                logger.debug(f"技能目录不存在，跳过: {directory}")
                continue

            loaded = self._scan_directory(directory, source)
            for name, skill in loaded.items():
                if name in self._skills:
                    existing = self._skills[name]
                    logger.info(
                        f"技能 '{name}' 被覆盖: {existing.source} -> {source}"
                    )
                self._skills[name] = skill

        # 更新缓存
        self._cache = {name: skill.meta for name, skill in self._skills.items()}

        logger.info(f"技能加载完成: 共 {len(self._skills)} 个技能")
        for name, skill in self._skills.items():
            logger.debug(f"  [{skill.source}] {name} ({skill.meta.type.value})")
        return self._skills

    def get_skill(self, name: str) -> Optional[Skill]:
        """获取指定名称的技能

        Args:
            name: 技能名称

        Returns:
            技能实例，如果不存在则返回 None
        """
        if not self._skills:
            self.discover_skills()
        return self._skills.get(name)

    def list_skills(self) -> list[SkillMeta]:
        """列出所有可用技能的元数据

        Returns:
            技能元数据列表
        """
        if not self._skills:
            self.discover_skills()
        return [skill.meta for skill in self._skills.values()]

    def list_skills_by_agent(self, agent_type: str) -> list[SkillMeta]:
        """按目标 Agent 类型筛选技能

        Args:
            agent_type: Agent 类型（coordinator / executor / analyzer）

        Returns:
            匹配的技能元数据列表
        """
        if not self._skills:
            self.discover_skills()
        return [
            skill.meta
            for skill in self._skills.values()
            if skill.meta.agent == agent_type
        ]

    def reload(self) -> dict[str, Skill]:
        """重新扫描所有目录并重新加载技能

        清空缓存后重新执行 discover_skills()。

        Returns:
            重新加载后的技能字典
        """
        logger.info("重新加载技能...")
        self._skills.clear()
        self._cache.clear()
        return self.discover_skills()

    # ── 内部方法 ──────────────────────────────────────────────

    def _scan_directory(self, directory: Path, source: str) -> dict[str, Skill]:
        """扫描指定目录下的所有 SKILL.md 文件并加载

        扫描规则：
        1. 递归搜索目录下所有的 SKILL.md 文件
        2. 解析 YAML frontmatter 获取元数据
        3. 根据元数据中的 name 字段注册技能

        Args:
            directory: 技能目录路径
            source: 技能来源标识（builtin / user / project）

        Returns:
            加载的技能字典
        """
        result: dict[str, Skill] = {}

        for skill_md in directory.rglob("SKILL.md"):
            try:
                skill = self._load_skill_file(skill_md, source)
                if skill.meta.name in result:
                    logger.warning(
                        f"目录 '{directory}' 中存在同名技能 '{skill.meta.name}' "
                        f"（{skill_md}），将使用先发现的"
                    )
                    continue
                result[skill.meta.name] = skill
                logger.debug(f"发现技能: [{source}] {skill.meta.name}")
            except Exception as e:
                logger.error(f"加载技能文件失败: {skill_md} - {e}")

        return result

    def _load_skill_file(self, file_path: Path, source: str) -> Skill:
        """从单个 SKILL.md 文件加载技能

        解析步骤：
        1. 读取文件全文
        2. 提取 YAML frontmatter（--- 之间的内容）
        3. 用 Pydantic 模型验证元数据
        4. 创建 Skill 实例

        Args:
            file_path: SKILL.md 文件路径
            source: 技能来源

        Returns:
            加载完成的 Skill 实例

        Raises:
            ValueError: frontmatter 缺失或格式错误
            FileNotFoundError: 文件不存在
        """
        if not file_path.exists():
            raise FileNotFoundError(f"技能文件不存在: {file_path}")

        content = file_path.read_text(encoding="utf-8")

        # 提取 YAML frontmatter
        frontmatter = self._extract_frontmatter(content)
        if not frontmatter:
            raise ValueError(
                f"技能文件 {file_path} 缺少 YAML frontmatter（--- 标记之间）"
            )

        # 解析元数据
        raw = yaml.safe_load(frontmatter)
        if not isinstance(raw, dict):
            raise ValueError(f"技能文件 {file_path} 的 frontmatter 格式错误")

        # 处理 type 字段：字符串转枚举
        if "type" in raw and isinstance(raw["type"], str):
            raw["type"] = SkillType(raw["type"])

        meta = SkillMeta(**raw)
        return Skill(meta=meta, content=content, path=file_path, source=source)

    @staticmethod
    def _extract_frontmatter(content: str) -> str | None:
        """从 Markdown 文本中提取 YAML frontmatter

        frontmatter 位于文件开头的两个 --- 之间：
        ---
        name: example
        description: ...
        ---

        Args:
            content: Markdown 全文

        Returns:
            frontmatter 原始文本，如果没有则返回 None
        """
        match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        if match:
            return match.group(1)
        return None

    # ── 工具方法 ──────────────────────────────────────────────

    @property
    def skill_dirs(self) -> dict[str, Path]:
        """获取所有技能目录路径"""
        return {
            "builtin": self._builtin_dir,
            "user": self._user_dir,
            "project": self._project_dir,
        }

    @property
    def skill_count(self) -> int:
        """已加载技能数量"""
        return len(self._skills)

    @property
    def skill_names(self) -> list[str]:
        """已加载技能名称列表"""
        if not self._skills:
            self.discover_skills()
        return sorted(self._skills.keys())
