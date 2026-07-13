# config/config.py
from pydantic import BaseModel, Field
from typing import Optional
import yaml
import os


class LogConfig(BaseModel):
    level: str = Field(default="INFO")
    file_path: str = Field(default="./logs/system.log")
    rotation: str = Field(default="100MB")
    retention: str = Field(default="7 days")
    json_format: bool = Field(default=False, description="是否启用 JSON 格式输出（生产环境建议开启）")


class DatabaseConfig(BaseModel):
    url: str = Field(default="", description="数据库连接 URL，为空则使用默认 SQLite")
    echo: bool = Field(default=False)


class AgentConfig(BaseModel):
    default_load_threshold: float = Field(default=0.8)
    auto_start: bool = Field(default=True)
    heartbeat_interval: int = Field(default=5)
    scheduler_poll_interval: float = Field(default=1.0, description="调度器轮询间隔（秒）")
    max_retries: int = Field(default=3, description="任务最大重试次数")


class StreamlitConfig(BaseModel):
    refresh_interval: int = Field(default=2)
    page_title: str = Field(default="MCASys 多Agent协作系统")
    page_icon: str = Field(default="🤖")


class ApiConfig(BaseModel):
    api_key: str = Field(default="", description="API 认证密钥，为空则自动生成")
    rate_limit: str = Field(default="100/minute", description="速率限制")
    cors_origins: list = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:8501"],
                                description="允许的 CORS 域名")


class LLMSettings(BaseModel):
    """LLM（大模型）配置 — 硅基流动 API"""
    api_key: str = Field(default="", description="硅基流动 API Key (env: SILICONFLOW_API_KEY)")
    base_url: str = Field(default="https://api.siliconflow.cn/v1", description="API 地址")
    model: str = Field(default="deepseek-ai/DeepSeek-V3.2", description="默认模型名称")
    max_tokens: int = Field(default=4096, description="最大生成 Token 数")
    temperature: float = Field(default=0.7, description="采样温度")


class AppConfig(BaseModel):
    log_config: LogConfig = Field(default_factory=LogConfig)
    database_config: DatabaseConfig = Field(default_factory=DatabaseConfig)
    agent_config: AgentConfig = Field(default_factory=AgentConfig)
    streamlit_config: StreamlitConfig = Field(default_factory=StreamlitConfig)
    api_config: ApiConfig = Field(default_factory=ApiConfig)
    llm_config: LLMSettings = Field(default_factory=LLMSettings)


def _apply_env_overrides(config: AppConfig) -> AppConfig:
    """从环境变量覆盖配置（优先级：环境变量 > YAML > 默认值）"""
    env_mapping = {
        "MCASYS_LOG_LEVEL": ("log_config", "level"),
        "MCASYS_LOG_JSON": ("log_config", "json_format", lambda v: v.lower() in ("true", "1", "yes")),
        "MCASYS_DB_URL": ("database_config", "url"),
        "MCASYS_AGENT_LOAD_THRESHOLD": ("agent_config", "default_load_threshold", float),
        "MCASYS_AGENT_MAX_RETRIES": ("agent_config", "max_retries", int),
        "MCASYS_SCHEDULER_INTERVAL": ("agent_config", "scheduler_poll_interval", float),
        "MCASYS_API_KEY": ("api_config", "api_key"),
        "MCASYS_CORS_ORIGINS": ("api_config", "cors_origins", lambda v: [o.strip() for o in v.split(",")]),
        "SILICONFLOW_API_KEY": ("llm_config", "api_key"),
        "SILICONFLOW_MODEL": ("llm_config", "model"),
        "SILICONFLOW_BASE_URL": ("llm_config", "base_url"),
    }

    for env_var, (section, field, *transform) in env_mapping.items():
        value = os.environ.get(env_var)
        if value is not None:
            if transform:
                try:
                    value = transform[0](value)
                except (ValueError, TypeError):
                    continue
            obj = getattr(config, section)
            if hasattr(obj, field):
                setattr(obj, field, value)

    return config


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """加载配置：YAML 文件 → 环境变量覆盖 → 验证"""
    config = AppConfig()

    if not config_path:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_dict = yaml.safe_load(f)
            if config_dict:
                config = AppConfig(**config_dict)
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件解析失败：{e}")
        except Exception as e:
            raise RuntimeError(f"加载配置文件出错：{e}")
    else:
        # 创建默认配置文件
        default_dict = AppConfig().model_dump()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(default_dict, f, indent=4, allow_unicode=True)
        print(f"默认配置文件已创建：{config_path}")

    # 环境变量覆盖
    config = _apply_env_overrides(config)
    return config


__all__ = ["LogConfig", "DatabaseConfig", "AgentConfig", "StreamlitConfig", "ApiConfig", "LLMSettings", "AppConfig", "load_config"]
