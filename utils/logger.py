# utils/logger.py
import sys
import json
import logging
from datetime import datetime
from loguru import logger
from dataclasses import dataclass


class LogConfig:
    """日志配置"""
    def __init__(self, level="INFO", file_path="./logs/system.log", rotation="100MB", retention="7 days", json_format=False):
        self.level = level
        self.file_path = file_path
        self.rotation = rotation
        self.retention = retention
        self.json_format = json_format


class StreamlitLogHandler(logging.Handler):
    """将日志转发到 Streamlit session_state"""

    def __init__(self):
        super().__init__()
        self._logs = []  # 环形缓冲区

    def emit(self, record):
        try:
            log_entry = {
                "time": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "name": record.name,
                "function": record.funcName,
                "line": record.lineno,
                "message": self.format(record),
            }
            self._logs.append(log_entry)
            if len(self._logs) > 500:
                self._logs = self._logs[-500:]
        except Exception:
            pass

    def get_recent_logs(self, count=100):
        return self._logs[-count:]


def json_formatter(record):
    """JSON 格式日志（适合 ELK/Loki 等日志聚合系统）"""
    log_entry = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ") if record["time"] else None,
        "level": record["level"].name,
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }
    if record["exception"]:
        log_entry["exception"] = str(record["exception"])
    extra = {k: v for k, v in record["extra"].items() if k not in ("name",)}
    if extra:
        log_entry["extra"] = extra
    return json.dumps(log_entry, default=str, ensure_ascii=False) + "\n"


_global_logger = None
_streamlit_handler = None


def streamlit_handler():
    global _streamlit_handler
    if _streamlit_handler is None:
        _streamlit_handler = StreamlitLogHandler()
    return _streamlit_handler


def init_logger(log_config: LogConfig = None):
    """初始化日志"""
    global _global_logger
    if _global_logger:
        return _global_logger

    if not log_config:
        log_config = LogConfig()

    logger.remove()

    # 文件输出
    if log_config.json_format:
        logger.add(
            log_config.file_path,
            level=log_config.level,
            rotation=log_config.rotation,
            retention=log_config.retention,
            encoding="utf-8",
            enqueue=True,
            format=json_formatter,
        )
    else:
        logger.add(
            log_config.file_path,
            level=log_config.level,
            rotation=log_config.rotation,
            retention=log_config.retention,
            encoding="utf-8",
            enqueue=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        )

    # 控制台输出
    logger.add(
        sys.stdout,
        level=log_config.level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # Streamlit 处理器
    logger.add(streamlit_handler(), level=log_config.level)

    _global_logger = logger
    return logger


def get_logger(name: str = "mcasys"):
    """获取 logger 实例"""
    if not _global_logger:
        init_logger()
    return _global_logger.bind(name=name)
