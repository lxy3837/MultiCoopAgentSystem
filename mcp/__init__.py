"""
MCASys MCP（Model Context Protocol）层

提供 MCP 协议兼容的客户端和服务器实现，
支持与外部 MCP 服务器集成，以及将 MCASys 内部能力
暴露为 MCP 工具供外部系统调用。
"""
from .types import (
    MCPServerType,
    MCPServerConfig,
    MCPConfig,
    MCPTool,
    MCPToolCallRequest,
    MCPToolCallResult,
    MCPResource,
    MCPPrompt,
)
from .config import MCPConfigManager
from .client import MCPClientManager
from .server import MCPServer

__all__ = [
    # 类型
    "MCPServerType",
    "MCPServerConfig",
    "MCPConfig",
    "MCPTool",
    "MCPToolCallRequest",
    "MCPToolCallResult",
    "MCPResource",
    "MCPPrompt",
    # 管理器
    "MCPConfigManager",
    "MCPClientManager",
    # 服务器
    "MCPServer",
]
