"""
MCP 配置管理器

管理 MCP 服务器配置的加载、保存、增删改查。
配置文件位于 config/mcp.json，格式为 JSON。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

from .types import MCPServerConfig

logger = get_logger("mcp.config")


class MCPConfigManager:
    """MCP 服务器配置管理器

    负责从 config/mcp.json 加载和持久化 MCP 服务器配置。
    如果配置文件不存在，会自动创建带有示例注释的默认配置。

    用法::

        manager = MCPConfigManager()
        servers = manager.list_servers()
        manager.add_server(some_config)
        manager.save()
    """

    def __init__(self, config_path: Optional[str] = None):
        """初始化配置管理器

        Args:
            config_path: 配置文件路径，默认为项目根目录下的 config/mcp.json
        """
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config",
                "mcp.json",
            )
        self._config_path = Path(config_path)
        self._servers: dict[str, MCPServerConfig] = {}
        self._load()

    # ── 配置加载与保存 ──

    def _load(self) -> None:
        """从配置文件加载 MCP 服务器配置"""
        if not self._config_path.exists():
            self._create_default_config()
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error("MCP 配置文件 JSON 解析失败: {error}", error=e)
            self._servers = {}
            return

        raw_servers = data.get("mcpServers", {})
        for name, cfg in raw_servers.items():
            # 跳过以 _ 开头的注释条目
            if name.startswith("_"):
                continue
            try:
                if "name" not in cfg:
                    cfg["name"] = name
                self._servers[name] = MCPServerConfig(**cfg)
            except Exception as e:
                logger.warning("跳过无效的 MCP 服务器配置 '{name}': {error}", name=name, error=e)

        logger.info("已加载 {count} 个 MCP 服务器配置", count=len(self._servers))

    def _create_default_config(self) -> None:
        """创建默认配置文件（含注释示例）"""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        default_config = {
            "mcpServers": {
                "_comment": "在此配置 MCP 服务器",
                "_example_brave_search": {
                    "type": "HTTP",
                    "url": "https://brave-search-mcp.example.com/mcp",
                    "headers": {"API_KEY": "your-key-here"},
                    "disabled": True,
                },
                "_example_filesystem": {
                    "type": "STDIO",
                    "command": "npx",
                    "args": ["-y", "@anthropic/mcp-server-filesystem", "~/Desktop"],
                    "disabled": True,
                },
            }
        }
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        logger.info("已创建默认 MCP 配置文件: {path}", path=self._config_path)

    def save(self) -> None:
        """将当前配置持久化到文件

        保存格式::

            {
              "mcpServers": {
                "server_name": { ... }
              }
            }
        """
        data = {
            "mcpServers": {
                name: cfg.model_dump()
                for name, cfg in self._servers.items()
            }
        }
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("MCP 配置已保存至: {path}", path=self._config_path)

    # ── 服务器管理 ──

    def add_server(self, config: MCPServerConfig) -> None:
        """添加一个新的 MCP 服务器

        Args:
            config: 服务器配置

        Raises:
            ValueError: 已存在同名服务器
        """
        if config.name in self._servers:
            raise ValueError(f"MCP 服务器 '{config.name}' 已存在")
        self._servers[config.name] = config
        logger.info("已添加 MCP 服务器: {name}", name=config.name)

    def remove_server(self, name: str) -> None:
        """移除一个 MCP 服务器

        Args:
            name: 服务器名称

        Raises:
            KeyError: 服务器不存在
        """
        if name not in self._servers:
            raise KeyError(f"MCP 服务器 '{name}' 不存在")
        del self._servers[name]
        logger.info("已移除 MCP 服务器: {name}", name=name)

    def list_servers(self) -> list[MCPServerConfig]:
        """列出所有已配置的 MCP 服务器

        Returns:
            服务器配置列表
        """
        return list(self._servers.values())

    def get_server(self, name: str) -> MCPServerConfig:
        """获取指定名称的服务器配置

        Args:
            name: 服务器名称

        Returns:
            服务器配置

        Raises:
            KeyError: 服务器不存在
        """
        if name not in self._servers:
            raise KeyError(f"MCP 服务器 '{name}' 不存在")
        return self._servers[name]

    def enable_server(self, name: str) -> None:
        """启用一个 MCP 服务器

        Args:
            name: 服务器名称
        """
        server = self.get_server(name)
        server.disabled = False
        logger.info("已启用 MCP 服务器: {name}", name=name)

    def disable_server(self, name: str) -> None:
        """禁用一个 MCP 服务器

        Args:
            name: 服务器名称
        """
        server = self.get_server(name)
        server.disabled = True
        logger.info("已禁用 MCP 服务器: {name}", name=name)

    @property
    def config_path(self) -> Path:
        """获取配置文件路径"""
        return self._config_path
