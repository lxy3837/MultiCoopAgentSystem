# data/models/task_model.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict

# 任务状态枚举
class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskModel(BaseModel):
    """任务数据模型"""
    task_id: str = Field(description="任务唯一ID")
    name: str = Field(description="任务名称")
    type: str = Field(description="任务类型：data_process/analysis/monitor/notification等")
    params: Dict = Field(default_factory=dict, description="任务参数（JSON格式）")
    status: str = Field(default=TaskStatus.PENDING, description="任务状态")
    executor_agent_id: Optional[str] = Field(default=None, description="执行该任务的Agent ID")
    create_time: datetime = Field(default_factory=datetime.now, description="任务创建时间")
    start_time: Optional[datetime] = Field(default=None, description="任务开始时间")
    end_time: Optional[datetime] = Field(default=None, description="任务结束时间")
    error_msg: Optional[str] = Field(default=None, description="任务失败时的错误信息")

    def model_dump(self):
        """兼容旧版pydantic的dict()方法"""
        return self.dict()

__all__ = ["TaskStatus", "TaskModel"]