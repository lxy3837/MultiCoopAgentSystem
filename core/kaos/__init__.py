"""
Kaos 环境抽象层 - 参考 kimi-code 的 kaos 包
"""
from ._base import (
    Kaos, Environment, StatResult, KaosProcess,
    KaosError, KaosFileNotFoundError, KaosPermissionError,
    KaosFileExistsError, KaosConnectionError, KaosValueError,
)
from .local import LocalKaos

__all__ = [
    "Kaos", "LocalKaos",
    "Environment", "StatResult", "KaosProcess",
    "KaosError", "KaosFileNotFoundError", "KaosPermissionError",
    "KaosFileExistsError", "KaosConnectionError", "KaosValueError",
]
