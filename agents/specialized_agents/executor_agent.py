# agents/specialized_agents/executor_agent.py
from agents.base_agent import BaseAgent, AgentState
from utils.logger import get_logger
from data import DataManager, TaskStatus


class ExecutorAgent(BaseAgent):
    """执行Agent：负责处理具体的任务（如数据处理、文件操作）"""

    def __init__(self, agent_id: str, agent_type: str = "executor"):
        super().__init__(agent_id, agent_type)
        self.logger = get_logger(f"executor_{agent_id}")
        self.data_manager = DataManager()

    def send_message(self, target_agent_id: str, message: dict):
        """实现消息发送逻辑"""
        self.logger.info(f"执行Agent {self.agent_id} 向 {target_agent_id} 发送消息：{message}")
        # 实际场景：对接CoordinatorAgent的通信器
        pass

    def execute_task(self, task: dict) -> dict:
        """核心：执行具体任务（模拟数据处理逻辑）"""
        self.update_state(status="running", load=0.8)  # 执行任务时负载升高
        self.logger.info(f"执行Agent {self.agent_id} 开始处理任务：{task['task_id']}")

        try:
            # 模拟任务执行（实际场景：替换为真实业务逻辑）
            task_type = task["type"]
            if task_type == "data_process":
                result = self._process_data(task["params"])
            elif task_type == "analysis":
                result = self._analyze_data(task["params"])
            else:
                result = {"code": -1, "msg": f"不支持的任务类型：{task_type}"}

            # 任务执行完成，更新状态
            self.update_state(status="idle", load=0.0)
            self.logger.info(f"执行Agent {self.agent_id} 完成任务：{task['task_id']}，结果：{result}")

            # 更新任务状态到DataManager
            task_model = self.data_manager.get_task_by_id(task["task_id"])
            if task_model:
                task_model.status = TaskStatus.COMPLETED
                task_model.end_time = self.state.updated_at
                self.data_manager.save_task(task_model)

            return result
        except Exception as e:
            # 任务执行失败
            self.update_state(status="error", load=0.0, error_msg=str(e))
            self.logger.error(f"执行Agent {self.agent_id} 处理任务失败：{e}")

            # 更新任务状态为失败
            task_model = self.data_manager.get_task_by_id(task["task_id"])
            if task_model:
                task_model.status = TaskStatus.FAILED
                task_model.error_msg = str(e)
                task_model.end_time = self.state.updated_at
                self.data_manager.save_task(task_model)

            return {"code": -1, "msg": str(e)}

    def _process_data(self, params: dict) -> dict:
        """模拟数据处理逻辑"""
        file_path = params.get("file_path", "")
        self.logger.info(f"处理数据文件：{file_path}")
        # 实际场景：读取文件、清洗数据、写入结果
        return {"code": 0, "msg": f"数据处理完成：{file_path}", "processed_rows": 1000}

    def _analyze_data(self, params: dict) -> dict:
        """模拟数据分析逻辑"""
        metric = params.get("metric", "sum")
        self.logger.info(f"分析数据，计算指标：{metric}")
        # 实际场景：计算统计指标、生成可视化
        return {"code": 0, "msg": f"数据分析完成，指标：{metric}", "result": 9527}


__all__ = ["ExecutorAgent"]