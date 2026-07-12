# agents/specialized_agents/analyzer_agent.py
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from agents.base_agent import BaseAgent
from core.event_bus import Event, EventType


class AnalyzerAgent(BaseAgent):
    """
    分析 Agent - 专注于数据分析、报表生成、趋势洞察
    """

    def __init__(self, agent_id: str, agent_type: str = "analyzer"):
        super().__init__(agent_id, agent_type)
        self._reports_dir = Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "workspace", "reports"))
        os.makedirs(self._reports_dir, exist_ok=True)

    async def on_startup(self):
        """启动时注册事件监听"""
        self.event_bus.subscribe(EventType.MESSAGE_RECEIVED, self._handle_message)
        self.event_bus.subscribe(EventType.TASK_COMPLETED, self._handle_task_completed)

    async def _handle_message(self, event: Event):
        """处理任务分配消息"""
        target = event.data.get("target", "")
        if target != self.agent_id:
            return
        msg = event.data.get("message", {})
        if msg.get("type") == "task_assignment":
            task = msg.get("task", {})
            await self.execute_task(task)

    async def _handle_task_completed(self, event: Event):
        """监听任务完成事件，可用于触发后续分析"""
        self.logger.info(f"分析 Agent 收到任务完成通知: {event.data.get('task_id')}")

    async def execute_task(self, task: dict) -> dict:
        """执行分析任务"""
        self.update_state(status="running", load=0.7)
        try:
            task_id = task.get("task_id", "unknown")
            params = task.get("params", {})
            report_type = params.get("report_type", "summary")

            self.logger.info(f"分析 Agent {self.agent_id} 开始生成报表: {task_id} ({report_type})")

            result = self._generate_report(report_type, params, task_id)

            self.update_state(status="idle", load=0.0)
            return result

        except Exception as e:
            self.update_state(status="error", load=0.0, error_msg=str(e))
            self.logger.error(f"分析 Agent {self.agent_id} 任务失败: {e}")
            return {"code": -1, "msg": str(e), "task_id": task.get("task_id")}

    def _generate_report(self, report_type: str, params: dict, task_id: str) -> dict:
        """生成分析报表"""
        handlers = {
            "summary": self._summary_report,
            "trend": self._trend_report,
            "comparison": self._comparison_report,
            "custom": self._custom_report,
        }
        handler = handlers.get(report_type, self._summary_report)
        return handler(params, task_id)

    def _summary_report(self, params: dict, task_id: str) -> dict:
        """
        汇总报表：基于输入数据生成统计摘要
        """
        data_source = params.get("data_source", [])
        title = params.get("title", f"汇总报表_{task_id}")

        report = {
            "title": title,
            "report_type": "summary",
            "generated_at": datetime.now().isoformat(),
            "generated_by": self.agent_id,
            "sections": [],
            "summary": {},
        }

        if not data_source:
            report["sections"].append({"name": "Overview", "content": "无数据源，生成空报表"})
            report["summary"] = {"total_records": 0, "status": "empty"}
        else:
            total_records = 0
            for source in data_source:
                if isinstance(source, dict):
                    total_records += source.get("count", 0)
                    report["sections"].append({
                        "name": source.get("name", "Unknown"),
                        "type": source.get("type", "raw"),
                        "count": source.get("count", 0),
                        "description": source.get("description", ""),
                    })

            report["summary"] = {
                "total_records": total_records,
                "total_sections": len(data_source),
                "status": "generated",
            }

        # 保存报表到文件
        report_path = self._save_report(task_id, report)
        report["report_path"] = report_path

        return {
            "code": 0,
            "msg": f"汇总报表生成完成: {title}",
            "report_path": report_path,
            "report": report,
        }

    def _trend_report(self, params: dict, task_id: str) -> dict:
        """
        趋势分析报表：分析时序数据趋势
        """
        data_points = params.get("data_points", [])
        metric = params.get("metric", "value")

        if not data_points:
            return {"code": -1, "msg": "趋势分析需要数据点"}

        # 计算趋势指标
        values = [d.get(metric, 0) for d in data_points if isinstance(d, dict)]
        if not values:
            return {"code": -1, "msg": "有效数据点不足"}

        # 趋势判断
        trend_direction = "stable"
        if len(values) >= 3:
            first_half = sum(values[:len(values) // 2]) / (len(values) // 2)
            second_half = sum(values[len(values) // 2:]) / (len(values) - len(values) // 2)
            if second_half > first_half * 1.1:
                trend_direction = "up"
            elif second_half < first_half * 0.9:
                trend_direction = "down"

        report = {
            "title": params.get("title", f"趋势分析_{task_id}"),
            "report_type": "trend",
            "generated_at": datetime.now().isoformat(),
            "generated_by": self.agent_id,
            "data_points": len(data_points),
            "metric": metric,
            "trend": {
                "direction": trend_direction,
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
                "start_value": values[0],
                "end_value": values[-1],
                "change_pct": round((values[-1] - values[0]) / max(abs(values[0]), 1) * 100, 2),
            },
        }

        report_path = self._save_report(task_id, report)
        return {"code": 0, "msg": "趋势分析完成", "report_path": report_path, "report": report}

    def _comparison_report(self, params: dict, task_id: str) -> dict:
        """
        对比分析报表：对比两组或多组数据
        """
        groups = params.get("groups", {})
        metrics = params.get("metrics", [])

        comparisons = {}
        for group_name, group_data in groups.items():
            comparisons[group_name] = {
                metric: {
                    "sum": sum(d.get(metric, 0) for d in group_data if isinstance(d, dict)),
                    "count": len(group_data),
                    "avg": None,
                }
                for metric in metrics
            }
            for metric in metrics:
                s = comparisons[group_name][metric]
                s["avg"] = round(s["sum"] / max(s["count"], 1), 2)

        report = {
            "title": params.get("title", f"对比分析_{task_id}"),
            "report_type": "comparison",
            "generated_at": datetime.now().isoformat(),
            "generated_by": self.agent_id,
            "comparisons": comparisons,
        }

        report_path = self._save_report(task_id, report)
        return {"code": 0, "msg": "对比分析完成", "report_path": report_path, "report": report}

    def _custom_report(self, params: dict, task_id: str) -> dict:
        """自定义报表"""
        report = {
            "title": params.get("title", f"自定义报表_{task_id}"),
            "report_type": "custom",
            "generated_at": datetime.now().isoformat(),
            "generated_by": self.agent_id,
            "custom_data": params.get("custom_data", {}),
        }
        report_path = self._save_report(task_id, report)
        return {"code": 0, "msg": "自定义报表生成完成", "report_path": report_path, "report": report}

    def _save_report(self, task_id: str, report: dict) -> str:
        """保存报表到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{task_id}_{timestamp}.json"
        filepath = self._reports_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        self.logger.info(f"报表已保存: {filepath}")
        return str(filepath)


__all__ = ["AnalyzerAgent"]
