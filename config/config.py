# config/config.py
from pydantic import BaseModel, Field
from typing import Optional
import yaml
import os


# 日志配置子模型
class LogConfig(BaseModel):
    level: str = Field(default="INFO", description="日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL")
    file_path: str = Field(default="./logs/system.log", description="日志文件存储路径")
    rotation: str = Field(default="100MB", description="日志文件滚动大小")
    retention: str = Field(default="7 days", description="日志保留时间")
    format: str = Field(
        default="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        description="日志输出格式"
    )


# Agent配置子模型
class AgentConfig(BaseModel):
    default_load_threshold: float = Field(default=0.8, description="Agent负载阈值（超过则不分配任务）")
    auto_start: bool = Field(default=True, description="系统启动时自动启动所有Agent")
    heartbeat_interval: int = Field(default=5, description="Agent心跳检测间隔（秒）")


# Streamlit配置子模型
class StreamlitConfig(BaseModel):
    refresh_interval: int = Field(default=2, description="UI自动刷新间隔（秒）")
    page_title: str = Field(default="MCASys 多Agent协作系统", description="UI页面标题")
    page_icon: str = Field(default="🤖", description="UI页面图标")


# 应用总配置模型
class AppConfig(BaseModel):
    log_config: LogConfig = Field(default_factory=LogConfig, description="日志配置")
    agent_config: AgentConfig = Field(default_factory=AgentConfig, description="Agent配置")
    streamlit_config: StreamlitConfig = Field(default_factory=StreamlitConfig, description="Streamlit配置")


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """
    加载配置文件（优先使用指定路径，否则用默认路径）
    :param config_path: 配置文件路径，默认使用 config/config.yaml
    :return: 结构化的AppConfig实例
    """
    # 默认配置文件路径
    if not config_path:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

    # 检查配置文件是否存在，不存在则创建默认配置
    if not os.path.exists(config_path):
        # 创建默认配置文件
        default_config = AppConfig().model_dump()
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, indent=4, allow_unicode=True)
        print(f"⚠️  默认配置文件不存在，已在 {config_path} 创建默认配置")
        return AppConfig()

    # 读取并解析配置文件
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)
        # 验证配置并返回结构化实例
        return AppConfig(**config_dict)
    except yaml.YAMLError as e:
        raise ValueError(f"配置文件解析失败：{e}")
    except Exception as e:
        raise RuntimeError(f"加载配置文件出错：{e}")


# 导出核心类/函数（供外部导入）
__all__ = ["LogConfig", "AgentConfig", "StreamlitConfig", "AppConfig", "load_config"]