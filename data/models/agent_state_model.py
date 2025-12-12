# data/models/agent_state_model.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class AgentStateModel(BaseModel):
    """Agent状态数据模型（与agents/base_agent.py的AgentState对应）"""
    agent_id: str = Field(description="Agent唯一ID")
    agent_type: str = Field(description="Agent类型：coordinator/executor/analyzer等")
    status: str = Field(default="idle", description="Agent状态：idle/running/error/stopped")
    load: float = Field(default=0.0, description="Agent负载（0.0 ~ 1.0）")
    error_msg: Optional[str] = Field(default="", description="错误信息（状态为error时填充）")
    updated_at: datetime = Field(default_factory=datetime.now, description="状态最后更新时间")

    def model_dump(self):
        """兼容旧版pydantic的dict()方法"""
        return self.dict()

__all__ = ["AgentStateModel"]