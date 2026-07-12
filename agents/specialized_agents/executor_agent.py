# agents/specialized_agents/executor_agent.py
import os
import json
import csv
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from agents.base_agent import BaseAgent
from core.event_bus import Event, EventType


class ExecutorAgent(BaseAgent):
    """
    执行 Agent - 处理数据处理、文件操作等实际任务
    支持真实业务：CSV/JSON 文件读写、数据转换、文件批量处理
    """

    def __init__(self, agent_id: str, agent_type: str = "executor"):
        super().__init__(agent_id, agent_type)
        self._work_dir = Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "workspace"))
        os.makedirs(self._work_dir, exist_ok=True)

    async def on_startup(self):
        """启动时注册事件监听"""
        self.event_bus.subscribe(EventType.MESSAGE_RECEIVED, self._handle_message)

    async def _handle_message(self, event: Event):
        """处理来自协调 Agent 的任务分配消息"""
        target = event.data.get("target", "")
        if target != self.agent_id:
            return
        msg = event.data.get("message", {})
        if msg.get("type") == "task_assignment":
            task = msg.get("task", {})
            self.logger.info(f"执行 Agent {self.agent_id} 收到任务分配: {task.get('task_id')}")
            await self.execute_task(task)

    async def execute_task(self, task: dict) -> dict:
        """执行任务入口"""
        self.update_state(status="running", load=0.8)
        try:
            task_id = task.get("task_id", "unknown")
            task_type = task.get("type", "data_process")
            params = task.get("params", {})

            self.logger.info(f"执行 Agent {self.agent_id} 开始执行任务: {task_id} ({task_type})")

            result = await self._dispatch(task_type, params, task_id)

            self.update_state(status="idle", load=0.0)
            return result

        except Exception as e:
            self.update_state(status="error", load=0.0, error_msg=str(e))
            self.logger.error(f"执行 Agent {self.agent_id} 任务失败: {e}")
            return {"code": -1, "msg": str(e), "task_id": task.get("task_id")}

    async def _dispatch(self, task_type: str, params: dict, task_id: str) -> dict:
        """根据任务类型分发到具体处理函数"""
        handlers = {
            "data_process": self._process_data,
            "file_convert": self._convert_file,
            "data_import": self._import_data,
            "batch_process": self._batch_process,
            "analysis": self._analyze_data,
        }
        handler = handlers.get(task_type, self._process_data)
        return await asyncio.to_thread(handler, params, task_id)

    # ---------- 真实业务逻辑 ----------

    def _process_data(self, params: dict, task_id: str) -> dict:
        """
        数据处理：读入 CSV/JSON，清洗转换，输出结果
        这是真实的文件 I/O 处理逻辑
        """
        input_path = params.get("input_path", "")
        output_format = params.get("output_format", "json")
        transformations = params.get("transformations", [])

        result_rows = 0
        output_file = None

        try:
            if not input_path or not os.path.exists(input_path):
                return {"code": -1, "msg": f"输入文件不存在: {input_path}"}

            # 读取输入
            data = self._read_file(input_path)
            if data is None:
                return {"code": -1, "msg": f"无法读取文件: {input_path}"}

            result_rows = len(data)

            # 应用数据转换
            for transform in transformations:
                data = self._apply_transform(data, transform)

            # 写入输出
            output_dir = self._work_dir / "outputs"
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = str(output_dir / f"{task_id}_{timestamp}.{output_format}")

            if output_format == "json":
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            elif output_format == "csv" and data:
                with open(output_file, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)

            return {
                "code": 0,
                "msg": f"数据处理完成",
                "input_rows": result_rows,
                "output_rows": len(data),
                "output_file": output_file,
                "transformations_applied": len(transformations),
            }
        except Exception as e:
            return {"code": -1, "msg": f"数据处理异常: {str(e)}"}

    def _convert_file(self, params: dict, task_id: str) -> dict:
        """文件格式转换：CSV <-> JSON <-> Excel"""
        input_path = params.get("input_path", "")
        to_format = params.get("to_format", "csv")

        if not input_path or not os.path.exists(input_path):
            return {"code": -1, "msg": f"输入文件不存在: {input_path}"}

        try:
            data = self._read_file(input_path)
            if data is None:
                return {"code": -1, "msg": "无法读取文件"}

            output_dir = self._work_dir / "outputs"
            os.makedirs(output_dir, exist_ok=True)
            output_file = str(output_dir / f"converted_{task_id}.{to_format}")

            if to_format == "json":
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            elif to_format == "csv" and data:
                with open(output_file, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)

            return {"code": 0, "msg": f"格式转换完成", "output_file": output_file}
        except Exception as e:
            return {"code": -1, "msg": str(e)}

    def _import_data(self, params: dict, task_id: str) -> dict:
        """
        数据导入：从外部文件批量导入到工作区
        """
        source_files = params.get("files", [])
        if not source_files:
            return {"code": -1, "msg": "未指定导入文件"}

        imported = []
        failed = []

        for src in source_files:
            try:
                if os.path.exists(src):
                    data = self._read_file(src)
                    imported.append({"file": src, "rows": len(data) if data else 0})
                else:
                    failed.append({"file": src, "reason": "文件不存在"})
            except Exception as e:
                failed.append({"file": src, "reason": str(e)})

        return {
            "code": 0 if not failed else 1,
            "msg": f"导入完成: {len(imported)} 成功, {len(failed)} 失败",
            "imported": imported,
            "failed": failed,
        }

    def _batch_process(self, params: dict, task_id: str) -> dict:
        """批量处理多个文件"""
        source_files = params.get("files", [])
        operation = params.get("operation", "count")

        results = []
        for src in source_files:
            try:
                data = self._read_file(src)
                row_count = len(data) if data else 0
                results.append({"file": src, "rows": row_count, "status": "ok"})
            except Exception as e:
                results.append({"file": src, "error": str(e), "status": "failed"})

        return {
            "code": 0,
            "msg": f"批量处理完成: {len(results)} 文件",
            "total_files": len(results),
            "results": results,
        }

    def _analyze_data(self, params: dict, task_id: str) -> dict:
        """
        数据分析：统计描述、聚合计算
        """
        input_path = params.get("input_path", "")
        metric = params.get("metric", "summary")

        if not input_path or not os.path.exists(input_path):
            return {"code": -1, "msg": f"输入文件不存在: {input_path}"}

        try:
            data = self._read_file(input_path)
            if not data:
                return {"code": -1, "msg": "数据为空"}

            if metric == "summary":
                result = self._compute_summary(data)
            elif metric == "count":
                result = {"count": len(data)}
            else:
                result = {"count": len(data), "metric": metric}

            return {"code": 0, "msg": "分析完成", "result": result}
        except Exception as e:
            return {"code": -1, "msg": str(e)}

    # ---------- 通用工具方法 ----------

    def _read_file(self, path: str):
        """通用文件读取：支持 CSV 和 JSON"""
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                with open(path, "r", encoding="utf-8") as f:
                    return list(csv.DictReader(f))
            elif ext == ".json":
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                # 尝试按文本读取
                with open(path, "r", encoding="utf-8") as f:
                    return [{"line": line.strip()} for line in f if line.strip()]
        except UnicodeDecodeError:
            self.logger.warning(f"UTF-8 解码失败，尝试 GBK: {path}")
            try:
                with open(path, "r", encoding="gbk") as f:
                    if ext == ".csv":
                        return list(csv.DictReader(f))
                    return [{"line": line.strip()} for line in f if line.strip()]
            except Exception:
                return None

    def _apply_transform(self, data: list, transform: dict) -> list:
        """应用数据转换"""
        op = transform.get("op", "filter")
        if op == "filter" and data:
            key = transform.get("key", "")
            value = transform.get("value", "")
            return [row for row in data if str(row.get(key, "")) != str(value)]
        elif op == "sort" and data:
            key = transform.get("key", "")
            reverse = transform.get("reverse", False)
            return sorted(data, key=lambda x: x.get(key, ""), reverse=reverse)
        elif op == "limit" and data:
            n = transform.get("n", 100)
            return data[:n]
        return data

    def _compute_summary(self, data: list) -> dict:
        """计算数据摘要统计"""
        if not data:
            return {}
        keys = list(data[0].keys())
        numeric_stats = {}
        for key in keys:
            try:
                values = [float(row.get(key, 0)) for row in data]
                numeric_stats[key] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": round(sum(values) / len(values), 2),
                    "sum": sum(values),
                }
            except (ValueError, TypeError):
                pass
        return {
            "total_rows": len(data),
            "columns": keys,
            "column_count": len(keys),
            "numeric_stats": numeric_stats,
        }


__all__ = ["ExecutorAgent"]
