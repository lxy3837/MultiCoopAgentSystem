"""
MCP 协议类型定义

定义 MCP (Model Context Protocol) 协议使用的核心数据模型，
包括服务器配置、工具定义、资源定义等。

参考：MCP 协议规范 (https://spec.modelcontextprotocol.io/)
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MCPServerType(str, Enum):
    """MCP 服务器连接类型"""
    HTTP = "HTTP"
    """HTTP 流式传输"""
    SSE = "SSE"
    """Server-Sent Events"""
    STDIO = "STDIO"
    """标准输入/输出（子进程）"""


class MCPServerConfig(BaseModel):
    """MCP 服务器连接配置

    描述如何连接到一个外部 MCP 服务器。
    支持三种连接方式：HTTP、SSE 和 STDIO。
    """
    name: str = Field(description="服务器名称，用作唯一标识符")
    type: MCPServerType = Field(default=MCPServerType.STDIO, description="连接类型")
    command: Optional[str] = Field(default=None, description="STDIO 模式的启动命令")
    args: list[str] = Field(default_factory=list, description="STDIO 模式的命令行参数")
    env: dict[str, str] = Field(default_factory=dict, description="STDIO 模式的环境变量")
    url: Optional[str] = Field(default=None, description="HTTP/SSE 模式的服务器 URL")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP/SSE 模式的请求头")
    disabled: bool = Field(default=False, description="是否禁用此服务器")


class MCPConfig(BaseModel):
    """MCP 顶层配置

    包含所有已配置的 MCP 服务器列表。
    配置文件格式为 JSON，存储于 config/mcp.json。
    """
    mcpServers: dict[str, MCPServerConfig] = Field(
        default_factory=dict,
        description="已配置的 MCP 服务器字典，键为服务器名称",
    )


class MCPTool(BaseModel):
    """MCP 工具定义

    表示从 MCP 服务器发现的一个可用工具。
    """
    name: str = Field(description="工具名称")
    description: str = Field(default="", description="工具功能描述")
    inputSchema: dict[str, Any] = Field(
        default_factory=dict,
        description="工具的 JSON Schema 输入参数定义",
    )


class MCPToolCallRequest(BaseModel):
    """MCP 工具调用请求

    向指定 MCP 服务器发起工具调用。
    """
    server_name: str = Field(description="目标 MCP 服务器名称")
    tool_name: str = Field(description="要调用的工具名称")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="工具调用参数",
    )


class MCPToolCallResult(BaseModel):
    """MCP 工具调用结果

    从 MCP 服务器返回的工具执行结果。
    """
    success: bool = Field(description="调用是否成功")
    content: Any = Field(default=None, description="工具返回的内容")
    error: Optional[str] = Field(default=None, description="错误信息（失败时）")


class MCPResource(BaseModel):
    """MCP 资源定义

    表示 MCP 服务器提供的一个资源（如文件、数据等）。
    """
    uri: str = Field(description="资源 URI")
    name: str = Field(description="资源名称")
    description: str = Field(default="", description="资源描述")
    mimeType: str = Field(default="text/plain", description="资源 MIME 类型")


class MCPPrompt(BaseModel):
    """MCP Prompt 定义

    表示 MCP 服务器提供的一个 Prompt 模板。
    """
    name: str = Field(description="Prompt 名称")
    description: str = Field(default="", description="Prompt 描述")
    arguments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Prompt 参数列表",
    )
