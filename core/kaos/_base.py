"""
Kaos 基类 + 类型定义 + 错误类型
分离出独立文件以消除循环导入
"""
from __future__ import annotations
import os
import stat as stat_module
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, Optional, List


# ---------- 错误类型 ----------

class KaosError(Exception):
    """Kaos 基类异常"""
    def __init__(self, message: str):
        super().__init__(message)
        self.name = self.__class__.__name__


class KaosFileNotFoundError(KaosError):
    """文件不存在"""
    pass


class KaosPermissionError(KaosError):
    """权限不足"""
    pass


class KaosFileExistsError(KaosError):
    """文件已存在"""
    pass


class KaosConnectionError(KaosError):
    """连接错误（SSH 等远程场景）"""
    pass


class KaosValueError(KaosError):
    """参数值错误"""
    pass


# ---------- 类型定义 ----------

@dataclass
class StatResult:
    """文件状态信息，镜像 Python os.stat_result"""
    st_mode: int
    st_ino: int = 0
    st_dev: int = 0
    st_nlink: int = 0
    st_uid: int = 0
    st_gid: int = 0
    st_size: int = 0
    st_atime: float = 0.0
    st_mtime: float = 0.0
    st_ctime: float = 0.0

    @classmethod
    def from_os_stat(cls, path: str) -> "StatResult":
        st = os.stat(path)
        return cls(
            st_mode=st.st_mode, st_ino=st.st_ino, st_dev=st.st_dev,
            st_nlink=st.st_nlink, st_uid=st.st_uid, st_gid=st.st_gid,
            st_size=st.st_size, st_atime=st.st_atime, st_mtime=st.st_mtime,
            st_ctime=st.st_ctime,
        )

    def is_dir(self) -> bool:
        return stat_module.S_ISDIR(self.st_mode)

    def is_file(self) -> bool:
        return stat_module.S_ISREG(self.st_mode)

    def is_symlink(self) -> bool:
        return stat_module.S_ISLNK(self.st_mode)


@dataclass
class Environment:
    """操作系统/Shell 环境信息"""
    platform: str
    shell: str
    home: str
    tmpdir: str
    encoding: str = "utf-8"


@dataclass
class KaosProcess:
    """进程句柄"""
    pid: int
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    _process: Optional[asyncio.subprocess.Process] = None

    async def wait(self) -> int:
        if self._process:
            self.returncode = await self._process.wait()
        return self.returncode or 0

    async def kill(self):
        if self._process:
            self._process.kill()
            await self._process.wait()


# ---------- Kaos 抽象基类 ----------

class Kaos(ABC):
    """环境抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def os_env(self) -> Environment:
        ...

    @abstractmethod
    def path_class(self) -> str:
        ...

    @abstractmethod
    def normpath(self, path: str) -> str:
        ...

    @abstractmethod
    def get_home(self) -> str:
        ...

    @abstractmethod
    def get_cwd(self) -> str:
        ...

    @abstractmethod
    async def chdir(self, path: str) -> None:
        ...

    @abstractmethod
    def with_cwd(self, cwd: str) -> "Kaos":
        ...

    @abstractmethod
    def with_env(self, env: Dict[str, str]) -> "Kaos":
        ...

    @abstractmethod
    async def stat(self, path: str, follow_symlinks: bool = True) -> StatResult:
        ...

    @abstractmethod
    async def iterdir(self, path: str) -> AsyncGenerator[str, None]:
        ...

    @abstractmethod
    async def glob(self, path: str, pattern: str) -> AsyncGenerator[str, None]:
        ...

    @abstractmethod
    async def read_bytes(self, path: str) -> bytes:
        ...

    @abstractmethod
    async def read_text(self, path: str, encoding: str = "utf-8", errors: str = "replace") -> str:
        ...

    @abstractmethod
    async def read_lines(self, path: str, encoding: str = "utf-8") -> AsyncGenerator[str, None]:
        ...

    @abstractmethod
    async def write_bytes(self, path: str, data: bytes) -> int:
        ...

    @abstractmethod
    async def write_text(self, path: str, data: str, encoding: str = "utf-8", mode: str = "w") -> int:
        ...

    @abstractmethod
    async def mkdir(self, path: str, parents: bool = True, exist_ok: bool = True) -> None:
        ...

    @abstractmethod
    async def exec(self, *args: str) -> KaosProcess:
        ...

    @abstractmethod
    async def exec_with_env(self, args: List[str], env: Optional[Dict[str, str]] = None) -> KaosProcess:
        ...
