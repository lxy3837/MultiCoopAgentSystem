"""
MCP 客户端管理器

管理到外部 MCP 服务器的连接，支持 STDIO（子进程）和 HTTP 两种传输方式。
遵循 JSON-RPC 2.0 协议与 MCP 服务器通信。

JSON-RPC 2.0 协议参考:
    - initialize: 握手和能力协商
    - tools/list: 发现服务器提供的工具
    - tools/call: 调用服务器工具
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Optional

import httpx

from utils.logger import get_logger

from .types import MCPServerConfig, MCPServerType, MCPTool, MCPToolCallResult

logger = get_logger("mcp.client")

# JSON-RPC 2.0 协议版本
JSONRPC_VERSION = "2.0"

# MCP 协议版本
MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPClientManager:
    """MCP 客户端管理器

    管理到多个外部 MCP 服务器的连接，提供工具发现和执行能力。
    支持 STDIO 子进程和 HTTP 两种传输方式。

    用法::

        manager = MCPClientManager()
        config = MCPServerConfig(name="my-server", type=MCPServerType.STIO, command="python", args=["server.py"])
        await manager.connect_server(config)
        tools = await manager.list_tools("my-server")
        result = await manager.call_tool("my-server", "echo", {"message": "hello"})
    """

    def __init__(self):
        self._connections: dict[str, _MCPConnection] = {}

    async def connect_server(self, config: MCPServerConfig) -> None:
        """连接到指定的 MCP 服务器

        根据配置的 type 字段自动选择连接方式（STDIO/HTTP/SSE）。

        Args:
            config: MCP 服务器配置

        Raises:
            ConnectionError: 连接失败
            ValueError: 不支持的连接类型或服务器已连接
        """
        if config.name in self._connections:
            raise ValueError(f"MCP 服务器 '{config.name}' 已连接")

        if config.disabled:
            logger.info("服务器 '{name}' 已被禁用，跳过连接", name=config.name)
            return

        if config.type == MCPServerType.STDIO:
            conn = _StdioConnection(config)
        elif config.type == MCPServerType.HTTP:
            conn = _HttpConnection(config)
        elif config.type == MCPServerType.SSE:
            conn = _HttpConnection(config)  # SSE 复用 HTTP 连接逻辑
            logger.warning("SSE 传输模式当前以 HTTP 模式运行")
        else:
            raise ValueError(f"不支持的连接类型: {config.type}")

        await conn.connect()
        self._connections[config.name] = conn
        logger.info("已连接到 MCP 服务器: {name} ({type})", name=config.name, type=config.type.value)

    async def disconnect_server(self, name: str) -> None:
        """断开与指定服务器的连接

        Args:
            name: 服务器名称

        Raises:
            KeyError: 服务器未连接
        """
        if name not in self._connections:
            raise KeyError(f"MCP 服务器 '{name}' 未连接")
        conn = self._connections.pop(name)
        await conn.disconnect()
        logger.info("已断开 MCP 服务器: {name}", name=name)

    async def list_tools(self, server_name: str) -> list[MCPTool]:
        """发现指定服务器的可用工具

        Args:
            server_name: 服务器名称

        Returns:
            可用工具列表

        Raises:
            KeyError: 服务器未连接
        """
        conn = self._get_connection(server_name)
        result = await conn.send_request("tools/list", {})
        tools_data = result.get("tools", [])
        return [
            MCPTool(
                name=t.get("name", ""),
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolCallResult:
        """调用指定服务器的工具

        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具调用参数

        Returns:
            工具调用结果

        Raises:
            KeyError: 服务器未连接
        """
        conn = self._get_connection(server_name)
        try:
            result = await conn.send_request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
            content = result.get("content", result)
            return MCPToolCallResult(success=True, content=content)
        except Exception as e:
            logger.error(
                "调用工具 '{tool}' 失败 (server={server}): {error}",
                tool=tool_name,
                server=server_name,
                error=e,
            )
            return MCPToolCallResult(success=False, error=str(e))

    async def list_all_tools(self) -> dict[str, list[MCPTool]]:
        """获取所有已连接服务器的工具列表

        Returns:
            服务器名称 -> 工具列表的字典
        """
        results = {}
        for name in list(self._connections.keys()):
            try:
                results[name] = await self.list_tools(name)
            except Exception as e:
                logger.error("获取服务器 '{name}' 工具列表失败: {error}", name=name, error=e)
                results[name] = []
        return results

    def is_connected(self, server_name: str) -> bool:
        """检查指定服务器是否已连接

        Args:
            server_name: 服务器名称

        Returns:
            True 如果已连接
        """
        return server_name in self._connections

    def get_connected_servers(self) -> list[str]:
        """获取所有已连接服务器名称列表

        Returns:
            已连接服务器名称列表
        """
        return list(self._connections.keys())

    async def disconnect_all(self) -> None:
        """断开所有连接"""
        names = list(self._connections.keys())
        for name in names:
            try:
                await self.disconnect_server(name)
            except Exception as e:
                logger.error("断开服务器 '{name}' 失败: {error}", name=name, error=e)

    def _get_connection(self, server_name: str) -> "_MCPConnection":
        """获取连接对象"""
        if server_name not in self._connections:
            raise KeyError(f"MCP 服务器 '{server_name}' 未连接")
        return self._connections[server_name]


# ── JSON-RPC 连接基类 ──


class _MCPConnection:
    """MCP 连接基类

    封装 JSON-RPC 2.0 的请求/响应协议。
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._request_id = 0

    async def connect(self) -> None:
        """建立连接并发起 initialize 握手"""
        raise NotImplementedError

    async def disconnect(self) -> None:
        """关闭连接"""
        raise NotImplementedError

    async def send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """发送 JSON-RPC 请求并获取结果

        Args:
            method: JSON-RPC 方法名
            params: 方法参数

        Returns:
            响应结果字典

        Raises:
            RuntimeError: JSON-RPC 错误
        """
        raise NotImplementedError

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @staticmethod
    def _validate_response(response: dict[str, Any]) -> dict[str, Any]:
        """验证 JSON-RPC 响应"""
        if "error" in response:
            error = response["error"]
            msg = error.get("message", str(error))
            raise RuntimeError(f"JSON-RPC 错误 (code={error.get('code')}): {msg}")
        if "result" not in response:
            raise RuntimeError(f"无效的 JSON-RPC 响应，缺少 result: {response}")
        return response["result"]

    @staticmethod
    def _build_init_request(req_id: int) -> dict[str, Any]:
        """构建 initialize 请求"""
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "MCASys",
                    "version": "1.0.0",
                },
            },
        }


# ── STDIO 连接实现 ──


class _StdioConnection(_MCPConnection):
    """通过标准输入/输出连接 MCP 服务器（子进程方式）"""

    def __init__(self, config: MCPServerConfig):
        super().__init__(config)
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_lock = asyncio.Lock()

    async def connect(self) -> None:
        """启动子进程并发起 initialize 握手"""
        if not self.config.command:
            raise ValueError("STDIO 模式必须指定 command")

        env = os.environ.copy()
        env.update(self.config.env)

        # 使用 CREATE_NO_WINDOW 在 Windows 上隐藏控制台窗口
        creationflags = 0
        if sys.platform == "win32":
            creationflags = 0x08000000  # CREATE_NO_WINDOW

        self._process = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            creationflags=creationflags if creationflags else None,
        )

        # initialize 握手
        init_request = self._build_init_request(self._next_id())
        await self._send_raw(init_request)
        response = await self._read_response()
        self._validate_response(response)

        # 发送 initialized 通知（无 id）
        await self._send_raw({"jsonrpc": JSONRPC_VERSION, "method": "notifications/initialized"})

        logger.info("STDIO 服务器 '{name}' 初始化完成", name=self.config.name)

    async def disconnect(self) -> None:
        """终止子进程"""
        if self._process:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass  # 进程已退出
            self._process = None

    async def send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """发送 JSON-RPC 请求并等待响应"""
        request = {
            "jsonrpc": JSONRPC_VERSION,
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        async with self._reader_lock:
            await self._send_raw(request)
            response = await self._read_response()

        return self._validate_response(response)

    async def _send_raw(self, message: dict[str, Any]) -> None:
        """发送原始 JSON-RPC 消息"""
        if not self._process or not self._process.stdin:
            raise RuntimeError("子进程未启动")
        payload = json.dumps(message, ensure_ascii=False) + "\n"
        self._process.stdin.write(payload.encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_response(self) -> dict[str, Any]:
        """从 stdout 读取一行 JSON 响应"""
        if not self._process or not self._process.stdout:
            raise RuntimeError("子进程未启动")
        line = await self._process.stdout.readline()
        if not line:
            raise ConnectionError("MCP 子进程已关闭 stdout")
        return json.loads(line.decode("utf-8"))


# ── HTTP 连接实现 ──


class _HttpConnection(_MCPConnection):
    """通过 HTTP 连接 MCP 服务器"""

    def __init__(self, config: MCPServerConfig):
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """建立 HTTP 客户端并发起 initialize 握手"""
        if not self.config.url:
            raise ValueError("HTTP/SSE 模式必须指定 url")

        self._client = httpx.AsyncClient(
            headers=self.config.headers,
            timeout=30.0,
        )

        # initialize 握手
        init_request = self._build_init_request(self._next_id())
        response = await self._client.post(self.config.url, json=init_request)
        response.raise_for_status()
        data = response.json()
        self._validate_response(data)

        # initialized 通知
        try:
            await self._client.post(
                self.config.url,
                json={"jsonrpc": JSONRPC_VERSION, "method": "notifications/initialized"},
            )
        except Exception:
            pass  # 通知失败不影响连接

        logger.info("HTTP 服务器 '{name}' 初始化完成", name=self.config.name)

    async def disconnect(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """发送 HTTP JSON-RPC 请求"""
        if not self._client:
            raise RuntimeError("HTTP 客户端未初始化")
        if not self.config.url:
            raise RuntimeError("HTTP URL 未配置")

        request = {
            "jsonrpc": JSONRPC_VERSION,
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        response = await self._client.post(self.config.url, json=request)
        response.raise_for_status()
        data = response.json()
        return self._validate_response(data)
