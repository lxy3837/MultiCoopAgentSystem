"""
MCP 本地服务器

通过标准输入/输出提供 JSON-RPC 2.0 协议的 MCP 服务器，
将 MCASys 内部能力暴露为 MCP 工具，供外部 MCP 客户端调用。

支持的工具:
    - system_info: 获取系统运行信息
    - agent_status: 查询 Agent 运行状态
    - task_create: 创建新任务
    - task_list: 列出所有任务
    - task_status: 查询任务状态

用法::

    python -m mcp.server
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import sys
from datetime import datetime
from typing import Any

from utils.logger import get_logger

logger = get_logger("mcp.server")

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"


# ── 工具定义 ──

_TOOLS = [
    {
        "name": "system_info",
        "description": "获取 MCASys 系统运行信息，包括系统资源、Python 版本、平台信息等。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "agent_status",
        "description": "查询指定 Agent 或所有 Agent 的运行状态。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "要查询的 Agent ID，为空则返回所有 Agent 状态",
                },
            },
        },
    },
    {
        "name": "task_create",
        "description": "在 MCASys 中创建一个新任务。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "任务名称",
                },
                "type": {
                    "type": "string",
                    "description": "任务类型，如 data_process、analysis、monitor",
                    "default": "data_process",
                },
                "params": {
                    "type": "object",
                    "description": "任务参数（JSON 对象）",
                    "default": {},
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "task_list",
        "description": "列出 MCASys 中的所有任务，可按状态过滤。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "按状态过滤：pending / running / completed / failed，为空则返回所有",
                },
            },
        },
    },
    {
        "name": "task_status",
        "description": "查询指定任务的详细信息。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "任务 ID",
                },
            },
            "required": ["task_id"],
        },
    },
]


class MCPServer:
    """MCP 本地服务器

    通过 stdin/stdout 与 MCP 客户端进行 JSON-RPC 2.0 通信，
    将 MCASys 内部能力暴露为 MCP 工具。

    启动方式::

        server = MCPServer()
        await server.run()
    """

    def __init__(self):
        self._running = False
        # 延迟导入，避免循环依赖
        self._app = None

    @property
    def app(self):
        """获取 FastAPI 应用实例（延迟加载）"""
        if self._app is None:
            try:
                from app import create_app
                self._app = create_app()
            except Exception as e:
                logger.warning("无法加载 FastAPI 应用: {error}", error=e)
        return self._app

    async def run(self) -> None:
        """启动 MCP 服务器主循环

        从 stdin 逐行读取 JSON-RPC 请求，
        处理后将结果写入 stdout。
        """
        self._running = True
        logger.info("MCP 本地服务器已启动，等待 JSON-RPC 请求...")

        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

        try:
            while self._running:
                line = await reader.readline()
                if not line:
                    break

                try:
                    request = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                response = await self._handle_request(request)
                if response is not None:
                    payload = json.dumps(response, ensure_ascii=False) + "\n"
                    writer.write(payload.encode("utf-8"))
                    await writer.drain()
        except Exception as e:
            logger.error("MCP 服务器异常: {error}", error=e)
        finally:
            self._running = False
            logger.info("MCP 服务器已停止")

    async def _handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """处理单个 JSON-RPC 请求

        Args:
            request: JSON-RPC 请求

        Returns:
            JSON-RPC 响应，通知类请求返回 None
        """
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        # 通知类请求（无 id），不回复
        if req_id is None:
            if method == "notifications/initialized":
                logger.info("收到 initialized 通知")
            return None

        try:
            result = await self._dispatch(method, params)
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "result": result,
            }
        except Exception as e:
            logger.error("处理请求失败 ({method}): {error}", method=method, error=e)
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": str(e),
                },
            }

    async def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        """路由分发：将 JSON-RPC 方法映射到具体处理函数"""
        handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "prompts/list": self._handle_prompts_list,
        }

        handler = handlers.get(method)
        if handler is None:
            raise RuntimeError(f"未知的方法: {method}")

        return await handler(params)

    # ── MCP 协议方法 ──

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 initialize 请求，返回服务器能力"""
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},
                "resources": {},
            },
            "serverInfo": {
                "name": "MCASys",
                "version": "1.0.0",
            },
        }

    async def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 tools/list 请求，返回可用工具列表"""
        return {"tools": _TOOLS}

    async def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 tools/call 请求，执行具体工具"""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool_handlers = {
            "system_info": self._tool_system_info,
            "agent_status": self._tool_agent_status,
            "task_create": self._tool_task_create,
            "task_list": self._tool_task_list,
            "task_status": self._tool_task_status,
        }

        handler = tool_handlers.get(tool_name)
        if handler is None:
            raise RuntimeError(f"未知的工具: {tool_name}")

        result = await handler(arguments)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, default=str),
                }
            ]
        }

    async def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 resources/list 请求"""
        return {"resources": []}

    async def _handle_prompts_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """处理 prompts/list 请求"""
        return {"prompts": []}

    # ── 工具实现 ──

    async def _tool_system_info(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """获取系统运行信息"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)
            disk = psutil.disk_usage(os.getcwd())
        except ImportError:
            mem = None
            cpu_percent = None
            disk = None

        info = {
            "platform": platform.platform(),
            "python_version": sys.version,
            "hostname": platform.node(),
            "cpu_percent": cpu_percent,
            "memory": {
                "total_gb": round(mem.total / (1024**3), 2) if mem else None,
                "available_gb": round(mem.available / (1024**3), 2) if mem else None,
                "percent": mem.percent if mem else None,
            } if mem else None,
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2) if disk else None,
                "free_gb": round(disk.free / (1024**3), 2) if disk else None,
            } if disk else None,
            "time": datetime.now().isoformat(),
        }
        return info

    async def _tool_agent_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """查询 Agent 运行状态"""
        agent_id = arguments.get("agent_id")
        # 从 data_storage/agent_states.json 读取 Agent 状态
        states_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data_storage",
            "agent_states.json",
        )

        try:
            with open(states_file, "r", encoding="utf-8") as f:
                all_states = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"agents": [], "message": "没有找到 Agent 状态数据"}

        if agent_id:
            agent_state = all_states.get(agent_id)
            if agent_state:
                return {"agents": [agent_state]}
            return {"agents": [], "message": f"未找到 Agent: {agent_id}"}

        return {"agents": list(all_states.values())}

    async def _tool_task_create(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """创建新任务"""
        task_name = arguments.get("name", "")
        task_type = arguments.get("type", "data_process")
        task_params = arguments.get("params", {})

        import uuid
        task_id = f"task_{uuid.uuid4().hex[:12]}"

        # 保存到 tasks.json
        tasks_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data_storage",
            "tasks.json",
        )

        task = {
            "task_id": task_id,
            "name": task_name,
            "type": task_type,
            "params": task_params,
            "status": "pending",
            "create_time": datetime.now().isoformat(),
            "executor_agent_id": arguments.get("executor_agent_id"),
        }

        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                tasks = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            tasks = {}

        tasks[task_id] = task

        os.makedirs(os.path.dirname(tasks_file), exist_ok=True)
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)

        logger.info("已创建任务: {name} ({task_id})", name=task_name, task_id=task_id)
        return {"task_id": task_id, "message": f"任务 '{task_name}' 已创建", "task": task}

    async def _tool_task_list(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """列出所有任务"""
        status_filter = arguments.get("status")

        tasks_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data_storage",
            "tasks.json",
        )

        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                all_tasks = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"tasks": [], "count": 0}

        tasks_list = list(all_tasks.values())
        if status_filter:
            tasks_list = [t for t in tasks_list if t.get("status") == status_filter]

        # 按创建时间降序排列
        tasks_list.sort(key=lambda t: t.get("create_time", ""), reverse=True)

        return {"tasks": tasks_list, "count": len(tasks_list)}

    async def _tool_task_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """查询任务状态"""
        task_id = arguments.get("task_id", "")

        tasks_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data_storage",
            "tasks.json",
        )

        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                all_tasks = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"error": "没有找到任务数据"}

        task = all_tasks.get(task_id)
        if task:
            return {"task": task}
        return {"error": f"未找到任务: {task_id}"}


def main():
    """MCP 服务器入口点"""
    server = MCPServer()
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("MCP 服务器已被用户终止")


if __name__ == "__main__":
    main()
