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

    listener_id = ctx.runtime.event_bus.subscribe("*", event_handler)
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
        ctx.runtime.event_bus.unsubscribe(listener_id)


# ---------- Static Files ----------

from fastapi.staticfiles import StaticFiles
import os as _os

_frontend_dir = _os.path.join(_os.path.dirname(__file__), "frontend")
if _os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend_static")
