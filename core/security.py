"""
安全模块 - API Key 认证管理
"""
import os
import hashlib
import secrets
from typing import Optional
from utils.logger import get_logger


class SecurityManager:
    """
    安全管理器
    - API Key 生成和验证
    - 默认从环境变量读取，支持自动生成
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.logger = get_logger("security")
        self._api_key: Optional[str] = None
        self._api_key_hash: Optional[str] = None
        self._initialized = True

    def init_api_key(self, key: str = None):
        """初始化 API Key"""
        if key:
            self._api_key = key
        else:
            self._api_key = os.environ.get("MCASYS_API_KEY")
            if not self._api_key:
                self._api_key = self._generate_key()
                self.logger.warning(
                    f"未设置 MCASYS_API_KEY 环境变量，已自动生成: {self._api_key[:8]}..."
                    "（请在生产环境中设置固定 Key）"
                )

        self._api_key_hash = hashlib.sha256(self._api_key.encode()).hexdigest()

    def _generate_key(self) -> str:
        """生成随机 API Key"""
        return f"mcasys_{secrets.token_hex(24)}"

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key

    def verify_key(self, key: str) -> bool:
        """验证 API Key"""
        if not self._api_key_hash:
            return False
        return hashlib.sha256(key.encode()).hexdigest() == self._api_key_hash

    def mask_key(self) -> str:
        """获取脱敏后的 Key（只显示前8位）"""
        if not self._api_key:
            return "not_initialized"
        return f"{self._api_key[:8]}..."


async def get_api_key() -> str:
    """获取 API Key（依赖注入用）"""
    return SecurityManager().api_key
