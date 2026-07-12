"""
AgentResult - 统一 Agent 返回类型
参考 ScriptForge AgentResult.java 设计

替代当前裸 dict {"code": 0, "msg": "..."} 模式，
提供更结构化的返回值，便于下游处理和错误传递。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum


class ResultCode(int, Enum):
    SUCCESS = 0
    FAILED = -1
    TIMEOUT = -2
    CANCELLED = -3
    RETRY_NEEDED = -4


@dataclass
class AgentResult:
    """
    统一 Agent 返回值

    参考 ScriptForge:
        AgentResult { success, data, metadata, errorMessage, durationMs }
    扩展为:
        code, data, msg, metadata, duration_ms, error
    """
    code: ResultCode = ResultCode.SUCCESS
    data: Any = None
    msg: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.code == ResultCode.SUCCESS

    @property
    def failed(self) -> bool:
        return self.code != ResultCode.SUCCESS

    # ── 静态工厂方法 ──

    @classmethod
    def ok(cls, data: Any = None, msg: str = "", **metadata) -> "AgentResult":
        """成功"""
        return cls(code=ResultCode.SUCCESS, data=data, msg=msg, metadata=metadata)

    @classmethod
    def fail(cls, msg: str = "", error: str = None, data: Any = None, code: ResultCode = ResultCode.FAILED, **metadata) -> "AgentResult":
        """失败"""
        return cls(code=code, data=data, msg=msg, error=error, metadata=metadata)

    @classmethod
    def timeout(cls, msg: str = "执行超时") -> "AgentResult":
        """超时"""
        return cls(code=ResultCode.TIMEOUT, msg=msg, error=msg)

    @classmethod
    def cancelled(cls, msg: str = "已取消") -> "AgentResult":
        """取消"""
        return cls(code=ResultCode.CANCELLED, msg=msg, error=msg)

    @classmethod
    def retry_needed(cls, msg: str = "需要重试", retry_count: int = 0) -> "AgentResult":
        """需要重试"""
        return cls(code=ResultCode.RETRY_NEEDED, msg=msg, metadata={"retry_count": retry_count})

    def with_duration(self, ms: float) -> "AgentResult":
        """设置执行耗时"""
        self.duration_ms = ms
        return self

    def with_meta(self, **kwargs) -> "AgentResult":
        """添加元数据"""
        self.metadata.update(kwargs)
        return self

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（API 返回）"""
        return {
            "code": self.code.value,
            "success": self.success,
            "msg": self.msg,
            "data": self.data,
            "metadata": self.metadata,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }
