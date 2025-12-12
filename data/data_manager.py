# data/data_manager.py
import json
import os
from datetime import datetime
from typing import List, Optional, Dict
from utils.logger import get_logger
from data.models.task_model import TaskModel, TaskStatus
from data.models.agent_state_model import AgentStateModel


class DataManager:
    """
    数据管理器：核心负责任务/Agent状态的持久化存储（JSON文件）
    支持功能：
    1. 任务CRUD（创建/读取/更新/删除）
    2. Agent状态保存/读取
    3. 自动创建存储目录/文件，避免路径不存在错误
    """

    def __init__(self):
        # 存储目录（项目根目录下的data_storage）
        self.storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_storage")
        # 任务存储文件
        self.task_file = os.path.join(self.storage_dir, "tasks.json")
        # Agent状态存储文件
        self.agent_state_file = os.path.join(self.storage_dir, "agent_states.json")

        # 初始化日志
        self.logger = get_logger("data_manager")

        # 自动创建存储目录和文件（不存在则创建）
        self._init_storage()

    def _init_storage(self):
        """初始化存储目录和默认文件"""
        # 创建存储目录
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
            self.logger.info(f"存储目录不存在，已创建：{self.storage_dir}")

        # 创建空任务文件（若不存在）
        if not os.path.exists(self.task_file):
            with open(self.task_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=4)
            self.logger.info(f"任务存储文件不存在，已创建：{self.task_file}")

        # 创建空Agent状态文件（若不存在）
        if not os.path.exists(self.agent_state_file):
            with open(self.agent_state_file, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=4)
            self.logger.info(f"Agent状态文件不存在，已创建：{self.agent_state_file}")

    # ------------------------------ 任务相关操作 ------------------------------
    def save_task(self, task: TaskModel) -> bool:
        """
        保存/更新任务（存在则更新，不存在则新增）
        :param task: TaskModel实例
        :return: 操作是否成功
        """
        try:
            # 读取现有任务
            with open(self.task_file, "r", encoding="utf-8") as f:
                tasks = json.load(f)

            # 转换TaskModel为可序列化字典（处理datetime）
            task_dict = task.model_dump()
            task_dict["create_time"] = task_dict["create_time"].isoformat() if task_dict["create_time"] else None
            task_dict["start_time"] = task_dict["start_time"].isoformat() if task_dict["start_time"] else None
            task_dict["end_time"] = task_dict["end_time"].isoformat() if task_dict["end_time"] else None

            # 检查任务是否已存在（按task_id）
            task_exists = False
            for i in range(len(tasks)):
                if tasks[i]["task_id"] == task.task_id:
                    tasks[i] = task_dict
                    task_exists = True
                    break
            # 不存在则新增
            if not task_exists:
                tasks.append(task_dict)

            # 写入文件
            with open(self.task_file, "w", encoding="utf-8") as f:
                json.dump(tasks, f, ensure_ascii=False, indent=4)

            self.logger.info(f"任务 {task.task_id} 已保存/更新")
            return True
        except Exception as e:
            self.logger.error(f"保存任务失败：{e}")
            return False

    def get_task_by_id(self, task_id: str) -> Optional[TaskModel]:
        """
        按ID查询任务
        :param task_id: 任务ID
        :return: TaskModel实例（None表示不存在）
        """
        try:
            with open(self.task_file, "r", encoding="utf-8") as f:
                tasks = json.load(f)

            # 查找任务
            for task_dict in tasks:
                if task_dict["task_id"] == task_id:
                    # 转换datetime字符串为datetime对象
                    task_dict["create_time"] = datetime.fromisoformat(task_dict["create_time"]) if task_dict[
                        "create_time"] else None
                    task_dict["start_time"] = datetime.fromisoformat(task_dict["start_time"]) if task_dict[
                        "start_time"] else None
                    task_dict["end_time"] = datetime.fromisoformat(task_dict["end_time"]) if task_dict[
                        "end_time"] else None
                    # 转换为TaskModel
                    return TaskModel(**task_dict)

            self.logger.warning(f"未找到任务：{task_id}")
            return None
        except Exception as e:
            self.logger.error(f"查询任务失败：{e}")
            return None

    def get_all_tasks(self, status: Optional[str] = None) -> List[TaskModel]:
        """
        查询所有任务（可按状态筛选）
        :param status: 任务状态（pending/running/completed/failed），None表示所有
        :return: TaskModel列表
        """
        try:
            with open(self.task_file, "r", encoding="utf-8") as f:
                tasks = json.load(f)

            task_list = []
            for task_dict in tasks:
                # 状态筛选
                if status and task_dict["status"] != status:
                    continue
                # 转换datetime
                task_dict["create_time"] = datetime.fromisoformat(task_dict["create_time"]) if task_dict[
                    "create_time"] else None
                task_dict["start_time"] = datetime.fromisoformat(task_dict["start_time"]) if task_dict[
                    "start_time"] else None
                task_dict["end_time"] = datetime.fromisoformat(task_dict["end_time"]) if task_dict["end_time"] else None
                # 转换为TaskModel
                task_list.append(TaskModel(**task_dict))

            self.logger.info(f"查询到 {len(task_list)} 条任务（状态筛选：{status or '所有'}）")
            return task_list
        except Exception as e:
            self.logger.error(f"查询所有任务失败：{e}")
            return []

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        :param task_id: 任务ID
        :return: 操作是否成功
        """
        try:
            with open(self.task_file, "r", encoding="utf-8") as f:
                tasks = json.load(f)

            # 过滤掉要删除的任务
            new_tasks = [t for t in tasks if t["task_id"] != task_id]
            if len(new_tasks) == len(tasks):
                self.logger.warning(f"删除任务失败：未找到任务 {task_id}")
                return False

            # 写入文件
            with open(self.task_file, "w", encoding="utf-8") as f:
                json.dump(new_tasks, f, ensure_ascii=False, indent=4)

            self.logger.info(f"任务 {task_id} 已删除")
            return True
        except Exception as e:
            self.logger.error(f"删除任务失败：{e}")
            return False

    # ------------------------------ Agent状态相关操作 ------------------------------
    def save_agent_state(self, agent_state: AgentStateModel) -> bool:
        """
        保存/更新Agent状态
        :param agent_state: AgentStateModel实例
        :return: 操作是否成功
        """
        try:
            with open(self.agent_state_file, "r", encoding="utf-8") as f:
                agent_states = json.load(f)

            # 转换AgentStateModel为可序列化字典
            state_dict = agent_state.model_dump()
            state_dict["updated_at"] = state_dict["updated_at"].isoformat()

            # 保存/更新
            agent_states[agent_state.agent_id] = state_dict

            # 写入文件
            with open(self.agent_state_file, "w", encoding="utf-8") as f:
                json.dump(agent_states, f, ensure_ascii=False, indent=4)

            self.logger.info(f"Agent {agent_state.agent_id} 状态已保存")
            return True
        except Exception as e:
            self.logger.error(f"保存Agent状态失败：{e}")
            return False

    def get_agent_state(self, agent_id: str) -> Optional[AgentStateModel]:
        """
        按ID查询Agent状态
        :param agent_id: Agent ID
        :return: AgentStateModel实例（None表示不存在）
        """
        try:
            with open(self.agent_state_file, "r", encoding="utf-8") as f:
                agent_states = json.load(f)

            if agent_id not in agent_states:
                self.logger.warning(f"未找到Agent状态：{agent_id}")
                return None

            # 转换数据
            state_dict = agent_states[agent_id]
            state_dict["updated_at"] = datetime.fromisoformat(state_dict["updated_at"])

            return AgentStateModel(**state_dict)
        except Exception as e:
            self.logger.error(f"查询Agent状态失败：{e}")
            return None

    def get_all_agent_states(self) -> Dict[str, AgentStateModel]:
        """
        查询所有Agent状态
        :return: {agent_id: AgentStateModel} 字典
        """
        try:
            with open(self.agent_state_file, "r", encoding="utf-8") as f:
                agent_states = json.load(f)

            result = {}
            for agent_id, state_dict in agent_states.items():
                state_dict["updated_at"] = datetime.fromisoformat(state_dict["updated_at"])
                result[agent_id] = AgentStateModel(**state_dict)

            self.logger.info(f"查询到 {len(result)} 个Agent状态")
            return result
        except Exception as e:
            self.logger.error(f"查询所有Agent状态失败：{e}")
            return {}

    # data/data_manager.py 中新增方法
    def delete_agent_state(self, agent_id: str) -> bool:
        """删除Agent状态"""
        try:
            with open(self.agent_state_file, "r", encoding="utf-8") as f:
                agent_states = json.load(f)

            if agent_id not in agent_states:
                self.logger.warning(f"删除Agent状态失败：{agent_id} 不存在")
                return False

            del agent_states[agent_id]
            with open(self.agent_state_file, "w", encoding="utf-8") as f:
                json.dump(agent_states, f, ensure_ascii=False, indent=4)

            self.logger.info(f"Agent {agent_id} 状态已删除")
            return True
        except Exception as e:
            self.logger.error(f"删除Agent状态失败：{e}")
            return False


# 导出核心类
__all__ = ["DataManager"]