# 核心函数：init_logger()、get_logger()
# 核心类：StreamlitLogHandler（适配Streamlit的日志处理器）
import logging
from loguru import logger
import sys
from dataclasses import dataclass


@dataclass
class LogConfig:
    """日志配置数据模型"""
    level: str = "INFO"
    file_path: str = "./logs/system.log"
    rotation: str = "100MB"
    retention: str = "7 days"


# 全局logger实例
_global_logger = None


class StreamlitLogHandler(logging.Handler):
    """自定义日志处理器：将日志输出到Streamlit UI"""

    def emit(self, record):
        """重写emit方法：适配Streamlit"""
        log_msg = self.format(record)
        # 实际场景：将日志存入全局缓存，供Streamlit日志页读取
        pass


def init_logger(log_config: LogConfig = None):
    """初始化日志配置"""
    global _global_logger
    if _global_logger:
        return _global_logger

    # 默认配置
    if not log_config:
        log_config = LogConfig()

    # 移除默认处理器
    logger.remove()

    # 添加文件处理器
    logger.add(
        log_config.file_path,
        level=log_config.level,
        rotation=log_config.rotation,
        retention=log_config.retention,
        encoding="utf-8",
        enqueue=True
    )

    # 添加控制台处理器
    logger.add(
        sys.stdout,
        level=log_config.level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # 添加Streamlit处理器
    logger.add(
        StreamlitLogHandler(),
        level=log_config.level
    )

    _global_logger = logger
    return logger


def get_logger(name: str = "mcasys"):
    """获取logger实例"""
    if not _global_logger:
        init_logger()
    return _global_logger.bind(name=name)