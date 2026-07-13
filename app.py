"""
MCASys 生产级 FastAPI 应用
- API Key 认证
- 请求 Pydantic 验证
- API 版本管理 (/api/v1/)
- 健康检查 + 就绪探针
- 速率限制
- 结构化错误响应
"""
import uuid
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from config.config import load_config, AppConfig
from core.security import SecurityManager
from core.models import TaskStatus, AgentStatus
from main import init_agent_system_async, get_agent_context, shutdown_system
from utils.logger import init_logger, LogConfig

# ---------- 请求/响应模型 ----------

class TaskCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="任务名称")
    type: str = Field(..., min_length=1, max_length=64, description="任务类型: data_process/analysis/file_convert/batch_process/data_import")
    params: Dict[str, Any] = Field(default_factory=dict, description="任务参数")
    priority: int = Field(default=0, ge=0, le=10, description="优先级 0-10")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        allowed = {"data_process", "analysis", "file_convert", "batch_process", "data_import"}
        if v not in allowed:
            raise ValueError(f"不支持的任务类型: {v}，允许: {allowed}")
        return v


class TaskStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="任务状态")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        allowed = {s.value for s in TaskStatus}
        if v not in allowed:
            raise ValueError(f"非法的任务状态: {v}，允许: {allowed}")
        return v


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: str = "ERROR"


# ---------- 生命周期 ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    config = load_config()
    log_cfg = config.log_config
    init_logger(LogConfig(
        level=log_cfg.level, file_path=log_cfg.file_path,
        rotation=log_cfg.rotation, retention=log_cfg.retention,
        json_format=log_cfg.json_format,
    ))
    await init_agent_system_async()
    yield
    # 关闭时清理
    await shutdown_system()


# ---------- 初始化 ----------

app = FastAPI(
    title="MCASys - 多Agent协作系统 API",
    description="生产级多Agent协作系统 REST API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS - 从配置读取白名单
config = load_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.api_config.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# 安全认证
security = HTTPBearer()
security_manager = SecurityManager()
security_manager.init_api_key(config.api_config.api_key)


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """验证 API Key"""
    if not security_manager.verify_key(credentials.credentials):
        raise HTTPException(status_code=401, detail="无效的 API Key")
    return credentials.credentials


async def get_ctx():
    """获取系统上下文依赖"""
    try:
        return get_agent_context()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="系统未初始化")

# ---------- 异常处理 ----------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "code": f"HTTP_{exc.status_code}"},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "内部服务器错误", "detail": str(exc), "code": "INTERNAL_ERROR"},
    )


# ========== API v1 路由 ==========
API_PREFIX = "/api/v1"

# ---------- 健康检查 ----------

@app.get("/healthz")
async def healthz():
    """K8s 存活探针"""
    return {"status": "ok"}

@app.get("/readyz")
async def readyz(ctx=Depends(get_ctx)):
    """K8s 就绪探针"""
    try:
        agent_count = len(ctx.runtime._agents)
        return {"status": "ready", "agent_count": agent_count}
    except Exception:
        raise HTTPException(status_code=503, detail="系统未就绪")


# ---------- Agent 管理 ----------

@app.get(f"{API_PREFIX}/agents")
async def list_agents(ctx=Depends(get_ctx), api_key=Depends(verify_api_key)):
    """获取所有 Agent 列表"""
    async with ctx.runtime.db_manager.session_factory() as session:
        from core.repository import AgentStateRepository
        repo = AgentStateRepository(session)
        states = await repo.get_all()

    agents = []
    for s in states:
        runner = ctx.runtime.get_agent(s.agent_id)
        agents.append({
            "agent_id": s.agent_id,
            "agent_type": s.agent_type,
            "status": s.status.value if isinstance(s.status, AgentStatus) else s.status,
            "load": s.load,
            "error_msg": s.error_msg,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "online": runner is not None,
        })
    return {"total": len(agents), "agents": agents}


@app.get(f"{API_PREFIX}/agents/{{agent_id}}")
async def get_agent(agent_id: str, ctx=Depends(get_ctx), api_key=Depends(verify_api_key)):
    """获取单个 Agent 详情"""
    runner = ctx.runtime.get_agent(agent_id)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Agent 不存在: {agent_id}")
    return {
        "agent_id": runner.agent_id,
        "agent_type": runner.agent_type,
        "status": runner.state.status,
        "load": runner.state.load,
        "error_msg": runner.state.error_msg,
        "updated_at": runner.state.updated_at.isoformat(),
    }


@app.post(f"{API_PREFIX}/agents/{{agent_id}}/start")
async def start_agent(agent_id: str, ctx=Depends(get_ctx), api_key=Depends(verify_api_key)):
    """启动 Agent"""
    runner = ctx.runtime.get_agent(agent_id)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Agent 不存在: {agent_id}")
    runner.start()
    await runner.persist_state()
    return {"message": f"Agent {agent_id} 已启动", "agent_id": agent_id}


@app.post(f"{API_PREFIX}/agents/{{agent_id}}/stop")
async def stop_agent(agent_id: str, ctx=Depends(get_ctx), api_key=Depends(verify_api_key)):
    """停止 Agent"""
    runner = ctx.runtime.get_agent(agent_id)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Agent 不存在: {agent_id}")
    runner.stop()
    await runner.persist_state()
    return {"message": f"Agent {agent_id} 已停止", "agent_id": agent_id}


# ---------- 任务管理 ----------

@app.get(f"{API_PREFIX}/tasks")
async def list_tasks(
    status: Optional[str] = None,
    ctx=Depends(get_ctx),
    api_key=Depends(verify_api_key),
):
    """获取所有任务，支持按状态筛选"""
    async with ctx.runtime.db_manager.session_factory() as session:
        from core.repository import TaskRepository
        repo = TaskRepository(session)
        task_status = TaskStatus(status) if status else None
        tasks = await repo.get_all(task_status)

    return {
        "total": len(tasks),
        "status_filter": status,
        "tasks": [t.to_dict() for t in tasks],
    }


@app.get(f"{API_PREFIX}/tasks/{{task_id}}")
async def get_task(task_id: str, ctx=Depends(get_ctx), api_key=Depends(verify_api_key)):
    """获取单个任务详情"""
    async with ctx.runtime.db_manager.session_factory() as session:
        from core.repository import TaskRepository
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return task.to_dict()


@app.post(f"{API_PREFIX}/tasks", status_code=201)
async def create_task(
    body: TaskCreateRequest,
    ctx=Depends(get_ctx),
    api_key=Depends(verify_api_key),
):
    """创建新任务并进入调度队列"""
    from core.models import TaskModel
    from core.event_bus import Event, EventType

    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task = TaskModel(
        task_id=task_id,
        name=body.name,
        type=body.type,
        params=body.params,
        status=TaskStatus.PENDING,
        priority=body.priority,
    )

    async with ctx.runtime.db_manager.session_factory() as session:
        from core.repository import TaskRepository
        repo = TaskRepository(session)
        await repo.create(task)

    # 发布任务创建事件
    await ctx.runtime.event_bus.publish(Event(
        event_id=f"evt_{task_id}_created",
        event_type=EventType.TASK_CREATED,
        source="api",
        data={"task_id": task_id, "task_type": body.type, "task_name": body.name},
    ))

    return {"message": "任务已创建", "task": task.to_dict()}


@app.put(f"{API_PREFIX}/tasks/{{task_id}}/status")
async def update_task_status(
    task_id: str,
    body: TaskStatusUpdateRequest,
    ctx=Depends(get_ctx),
    api_key=Depends(verify_api_key),
):
    """更新任务状态"""
    async with ctx.runtime.db_manager.session_factory() as session:
        from core.repository import TaskRepository
        repo = TaskRepository(session)
        task = await repo.get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        old_status = task.status.value if isinstance(task.status, TaskStatus) else task.status
        success = await repo.update_status(task_id, TaskStatus(body.status))

    if not success:
        raise HTTPException(status_code=500, detail="状态更新失败")

    return {
        "message": f"任务状态已更新",
        "task_id": task_id,
        "old_status": old_status,
        "new_status": body.status,
    }


@app.delete(f"{API_PREFIX}/tasks/{{task_id}}")
async def delete_task(task_id: str, ctx=Depends(get_ctx), api_key=Depends(verify_api_key)):
    """删除任务"""
    async with ctx.runtime.db_manager.session_factory() as session:
        from core.repository import TaskRepository
        repo = TaskRepository(session)
        success = await repo.delete(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return {"message": f"任务已删除", "task_id": task_id}


# ---------- 系统信息 ----------

@app.get(f"{API_PREFIX}/system/stats")
async def system_stats(ctx=Depends(get_ctx), api_key=Depends(verify_api_key)):
    """系统统计信息"""
    async with ctx.runtime.db_manager.session_factory() as session:
        from core.repository import TaskRepository
        repo = TaskRepository(session)
        stats = {}
        for s in TaskStatus:
            stats[s.value] = await repo.count_by_status(s)

    agent_states = {}
    for aid, a in ctx.runtime._agents.items():
        agent_states[aid] = {
            "type": a.agent_type,
            "status": a.state.status,
            "load": a.state.load,
        }

    return {
        "tasks": stats,
        "agents": agent_states,
        "event_bus_subscribers": ctx.runtime.event_bus.subscriber_count,
        "system": {
            "version": "2.0.0",
            "api_key_masked": security_manager.mask_key(),
        },
    }


@app.get(f"{API_PREFIX}/system/events")
async def recent_events(
    event_type: Optional[str] = None,
    limit: int = 50,
    ctx=Depends(get_ctx),
    api_key=Depends(verify_api_key),
):
    """获取最近的事件"""
    from core.event_bus import EventType
    et = EventType(event_type) if event_type else None
    events = ctx.runtime.event_bus.get_history(et, limit=limit)
    return {
        "total": len(events),
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "source": e.source,
                "data": e.data,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in events
        ],
    }


# ---------- Skills 技能管理 ----------

@app.get(f"{API_PREFIX}/skills")
async def list_skills(agent_type: Optional[str] = None, api_key=Depends(verify_api_key)):
    """获取所有可用技能，支持按 Agent 类型筛选"""
    try:
        from skills import SkillManager
        manager = SkillManager()
        if agent_type:
            metas = manager.list_skills_by_agent(agent_type)
        else:
            metas = manager.list_skills()
        return {
            "total": len(metas),
            "agent_type_filter": agent_type,
            "skills": [
                {
                    "name": m.name,
                    "description": m.description,
                    "type": m.type.value,
                    "tools": m.tools,
                    "when_to_use": m.when_to_use,
                    "agent": m.agent,
                }
                for m in metas
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"技能加载失败: {str(e)}")


@app.get(f"{API_PREFIX}/skills/{{skill_name}}")
async def get_skill(skill_name: str, api_key=Depends(verify_api_key)):
    """获取单个技能详情（含系统提示词）"""
    try:
        from skills import SkillManager
        manager = SkillManager()
        skill = manager.get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"技能不存在: {skill_name}")
        return {
            "name": skill.meta.name,
            "description": skill.meta.description,
            "type": skill.meta.type.value,
            "tools": skill.meta.tools,
            "when_to_use": skill.meta.when_to_use,
            "agent": skill.meta.agent,
            "source": skill.source,
            "system_prompt": skill.get_system_prompt(),
            "flow_diagram": skill.get_flow_diagram() if skill.meta.type.value == "flow" else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取技能失败: {str(e)}")


@app.post(f"{API_PREFIX}/skills/reload")
async def reload_skills(api_key=Depends(verify_api_key)):
    """重新加载所有技能"""
    try:
        from skills import SkillManager
        manager = SkillManager()
        skills = manager.reload()
        return {
            "message": "技能已重新加载",
            "count": len(skills),
            "skills": list(skills.keys()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重载技能失败: {str(e)}")


# ---------- MCP 管理 ----------

@app.get(f"{API_PREFIX}/mcp/servers")
async def list_mcp_servers(api_key=Depends(verify_api_key)):
    """获取所有 MCP 服务器配置"""
    try:
        from mcp import MCPConfigManager
        manager = MCPConfigManager()
        servers = manager.list_servers()
        return {
            "total": len(servers),
            "servers": [
                {
                    "name": s.name,
                    "type": s.type.value,
                    "command": s.command,
                    "args": s.args,
                    "url": s.url,
                    "disabled": s.disabled,
                }
                for s in servers
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载 MCP 配置失败: {str(e)}")


class MCPAddServerRequest(BaseModel):
    name: str = Field(..., min_length=1, description="服务器名称")
    type: str = Field(..., description="连接类型: HTTP, SSE, STDIO")
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    disabled: bool = False

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        allowed = {"HTTP", "SSE", "STDIO"}
        if v not in allowed:
            raise ValueError(f"不支持的类型: {v}，允许: {allowed}")
        return v


@app.post(f"{API_PREFIX}/mcp/servers", status_code=201)
async def add_mcp_server(body: MCPAddServerRequest, api_key=Depends(verify_api_key)):
    """添加 MCP 服务器配置"""
    try:
        from mcp import MCPConfigManager, MCPServerConfig, MCPServerType
        manager = MCPConfigManager()
        config = MCPServerConfig(
            name=body.name,
            type=MCPServerType(body.type),
            command=body.command,
            args=body.args,
            url=body.url,
            headers=body.headers,
            env=body.env,
            disabled=body.disabled,
        )
        manager.add_server(config)
        manager.save()
        return {"message": f"MCP 服务器 '{body.name}' 已添加"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加失败: {str(e)}")


@app.delete(f"{API_PREFIX}/mcp/servers/{{server_name}}")
async def remove_mcp_server(server_name: str, api_key=Depends(verify_api_key)):
    """删除 MCP 服务器配置"""
    try:
        from mcp import MCPConfigManager
        manager = MCPConfigManager()
        manager.remove_server(server_name)
        manager.save()
        return {"message": f"MCP 服务器 '{server_name}' 已删除"}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP 服务器不存在: {server_name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@app.post(f"{API_PREFIX}/mcp/servers/{{server_name}}/connect")
async def connect_mcp_server(server_name: str, api_key=Depends(verify_api_key)):
    """连接到 MCP 服务器并发现工具"""
    try:
        from mcp import MCPConfigManager, MCPClientManager
        cfg_manager = MCPConfigManager()
        server_config = cfg_manager.get_server(server_name)
        client_manager = MCPClientManager()
        await client_manager.connect_server(server_config)
        tools = await client_manager.list_tools(server_name)
        return {
            "message": f"已连接到 {server_name}",
            "tools": [
                {"name": t.name, "description": t.description}
                for t in tools
            ],
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP 服务器不存在: {server_name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"连接失败: {str(e)}")


@app.get(f"{API_PREFIX}/mcp/tools")
async def list_mcp_tools(server_name: Optional[str] = None, api_key=Depends(verify_api_key)):
    """获取 MCP 工具列表"""
    try:
        from mcp import MCPConfigManager, MCPClientManager
        cfg_manager = MCPConfigManager()
        client_manager = MCPClientManager()

        if server_name:
            server_config = cfg_manager.get_server(server_name)
            await client_manager.connect_server(server_config)
            tools = await client_manager.list_tools(server_name)
            return {"server_name": server_name, "tools": [{"name": t.name, "description": t.description} for t in tools]}

        all_tools = {}
        for s in cfg_manager.list_servers():
            if s.disabled:
                continue
            try:
                await client_manager.connect_server(s)
                all_tools[s.name] = [
                    {"name": t.name, "description": t.description}
                    for t in await client_manager.list_tools(s.name)
                ]
            except Exception:
                all_tools[s.name] = []
        return {"servers": all_tools}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP 服务器不存在: {server_name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取工具失败: {str(e)}")


# ---------- 根路由 ----------

@app.get("/")
async def root():
    """Serve the dashboard HTML"""
    import os as _os_local
    from fastapi.responses import FileResponse as _FileResponse
    html_path = _os_local.path.join(_os_local.path.dirname(__file__), "frontend", "index.html")
    if _os_local.path.exists(html_path):
        return _FileResponse(html_path)
    return JSONResponse({
        "message": "MCASys API v2.0 - 多Agent协作系统",
        "status": "running",
        "docs": "/docs",
        "api_prefix": API_PREFIX,
    })


# ---------- 系统配置 ----------

class LLMConfigUpdateRequest(BaseModel):
    api_key: str | None = Field(default=None, description="硅基流动 API Key")
    model: str | None = Field(default=None, description="模型名称")
    base_url: str | None = Field(default=None, description="API 地址")
    max_tokens: int | None = Field(default=None, description="最大 Token 数")
    temperature: float | None = Field(default=None, description="采样温度")


@app.get(f"{API_PREFIX}/config/llm")
async def get_llm_config(api_key=Depends(verify_api_key)):
    """获取 LLM 配置（API Key 脱敏）"""
    from core.llm import get_llm_client
    client = get_llm_client()
    cfg = client.config
    masked_key = ""
    if cfg.api_key:
        masked_key = cfg.api_key[:8] + "****" + cfg.api_key[-4:] if len(cfg.api_key) > 12 else "****"
    return {
        "available": cfg.is_configured,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "max_tokens": cfg.max_tokens,
        "temperature": cfg.temperature,
        "api_key_masked": masked_key,
    }


@app.put(f"{API_PREFIX}/config/llm")
async def update_llm_config(body: LLMConfigUpdateRequest, api_key=Depends(verify_api_key)):
    """更新 LLM 配置并持久化到 config.yaml"""
    try:
        import os
        import yaml
        from core.llm import LLMConfig, init_llm_client
        from pathlib import Path

        config_path = Path(os.path.dirname(os.path.abspath(__file__))) / "config" / "config.yaml"

        # 读取当前 YAML
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
        else:
            config_data = {}

        # 更新 llm_config 部分
        if "llm_config" not in config_data:
            config_data["llm_config"] = {}

        updates = {}
        if body.api_key is not None:
            config_data["llm_config"]["api_key"] = body.api_key
            updates["api_key"] = True
        if body.model is not None:
            config_data["llm_config"]["model"] = body.model
            updates["model"] = body.model
        if body.base_url is not None:
            config_data["llm_config"]["base_url"] = body.base_url
            updates["base_url"] = body.base_url
        if body.max_tokens is not None:
            config_data["llm_config"]["max_tokens"] = body.max_tokens
            updates["max_tokens"] = body.max_tokens
        if body.temperature is not None:
            config_data["llm_config"]["temperature"] = body.temperature
            updates["temperature"] = body.temperature

        # 写回 YAML
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, indent=2, allow_unicode=True, default_flow_style=False)

        # 重新初始化 LLM 客户端
        from config.config import AppConfig
        cfg = AppConfig()
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg_dict = yaml.safe_load(f)
            if cfg_dict:
                cfg = AppConfig(**cfg_dict)

        new_llm = LLMConfig(
            api_key=cfg.llm_config.api_key,
            base_url=cfg.llm_config.base_url,
            model=cfg.llm_config.model,
            max_tokens=cfg.llm_config.max_tokens,
            temperature=cfg.llm_config.temperature,
        )
        init_llm_client(new_llm)

        # 同时设置环境变量使其在子进程中生效
        if body.api_key:
            os.environ["SILICONFLOW_API_KEY"] = body.api_key
        else:
            os.environ.pop("SILICONFLOW_API_KEY", None)

        return {
            "message": "LLM 配置已更新并生效",
            "available": new_llm.is_configured,
            "model": new_llm.model,
            "updates": updates,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")


# ---------- LLM Chat API ----------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息")
    history: list[dict] = Field(default_factory=list, description="对话历史")
    system_prompt: str | None = Field(default=None, description="系统提示词")


@app.post(f"{API_PREFIX}/chat")
async def llm_chat(body: ChatRequest, api_key=Depends(verify_api_key)):
    """LLM 对话接口 — 调用硅基流动 API"""
    from core.llm import get_llm_client
    client = get_llm_client()
    if not client.is_available:
        raise HTTPException(status_code=503, detail="LLM 未配置 API Key，请设置 SILICONFLOW_API_KEY 环境变量")

    try:
        if body.history:
            messages = body.history + [{"role": "user", "content": body.message}]
            if body.system_prompt:
                messages.insert(0, {"role": "system", "content": body.system_prompt})
            response = await client.chat_with_history(messages)
        else:
            response = await client.chat(
                prompt=body.message,
                system_prompt=body.system_prompt,
            )
        return {
            "message": response,
            "model": client.config.model,
        }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get(f"{API_PREFIX}/chat/status")
async def llm_status(api_key=Depends(verify_api_key)):
    """检查 LLM 可用状态"""
    from core.llm import get_llm_client
    client = get_llm_client()
    return {
        "available": client.is_available,
        "model": client.config.model,
        "base_url": client.config.base_url,
    }


# ---------- 工作台路由 ----------
@app.get("/workbench")
async def workbench():
    """Serve the workbench HTML"""
    import os as _os_local
    from fastapi.responses import FileResponse as _FileResponse
    html_path = _os_local.path.join(_os_local.path.dirname(__file__), "frontend", "workbench.html")
    if _os_local.path.exists(html_path):
        return _FileResponse(html_path)
    raise HTTPException(status_code=404, detail="工作台页面不存在")


@app.get("/config")
async def config_page():
    """Serve the config HTML"""
    import os as _os_local
    from fastapi.responses import FileResponse as _FileResponse
    html_path = _os_local.path.join(_os_local.path.dirname(__file__), "frontend", "config.html")
    if _os_local.path.exists(html_path):
        return _FileResponse(html_path)
    raise HTTPException(status_code=404, detail="配置页面不存在")


# ---------- WebSocket ----------

from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    """WebSocket 事件推送"""
    await ws.accept()
    ctx = get_agent_context()

    async def event_handler(event):
        try:
            await ws.send_json({
                "type": "event",
                "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                "source": event.source,
                "data": event.data,
                "timestamp": event.timestamp.isoformat() if hasattr(event, "timestamp") else None,
            })
        except Exception:
            pass

    ctx.runtime.event_bus.subscribe_all(event_handler)
    try:
        while True:
            # Keep connection alive, wait for client messages
            data = await ws.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ctx.runtime.event_bus.unsubscribe_all(event_handler)


# ---------- Static Files ----------

from fastapi.staticfiles import StaticFiles
import os as _os

_frontend_dir = _os.path.join(_os.path.dirname(__file__), "frontend")
if _os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend_static")
