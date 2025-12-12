# agents/specialized_agents/analyzer_agent.py
from agents.base_agent import BaseAgent, AgentState
from utils.logger import get_logger
from data import DataManager, TaskStatus


class AnalyzerAgent(BaseAgent):
    """分析Agent：专注于数据分析/报表生成类任务"""

    def __init__(self, agent_id: str, agent_type: str = "analyzer"):
        super().__init__(agent_id, agent_type)
        self.logger = get_logger(f"analyzer_{agent_id}")
        self.data_manager = DataManager()

    def send_message(self, target_agent_id: str, message: dict):
        self.logger.info(f"分析Agent {self.agent_id} 向 {target_agent_id} 发送消息：{message}")
        pass

    def execute_task(self, task: dict) -> dict:
        self.update_state(status="running", load=0.7)
        self.logger.info(f"分析Agent {self.agent_id} 开始处理分析任务：{task['task_id']}")

        try:
            # 模拟分析任务（生成报表）
            report_type = task["params"].get("report_type", "summary")
            result = {
                "code": 0,
                "msg": f"分析报表生成完成：{report_type}",
                "report_path": f"./reports/{task['task_id']}_{report_type}.pdf"
            }

            self.update_state(status="idle", load=0.0)
            # 更新任务状态
            task_model = self.data_manager.get_task_by_id(task["task_id"])
            if task_model:
                task_model.status = TaskStatus.COMPLETED
                task_model.end_time = self.state.updated_at
                self.data_manager.save_task(task_model)

            return result
        except Exception as e:
            self.update_state(status="error", load=0.0, error_msg=str(e))
            # 更新任务状态为失败
            task_model = self.data_manager.get_task_by_id(task["task_id"])
            if task_model:
                task_model.status = TaskStatus.FAILED
                task_model.error_msg = str(e)
                self.data_manager.save_task(task_model)

            return {"code": -1, "msg": str(e)}


__all__ = ["AnalyzerAgent"]