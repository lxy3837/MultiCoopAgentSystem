"""
LocalKaos - 本地环境实现
参考 kimi-code local.ts 设计
"""
from __future__ import annotations
import os
import sys
import asyncio
import subprocess
import fnmatch
import glob as glob_module
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from ._base import (
    Kaos, Environment, StatResult, KaosProcess,
    KaosError, KaosFileNotFoundError, KaosPermissionError, KaosFileExistsError,
)


def _detect_environment() -> Environment:
    platform = sys.platform
    shell = os.environ.get("COMSPEC", "cmd.exe") if platform == "win32" else os.environ.get("SHELL", "/bin/sh")
    home = str(Path.home())
    tmpdir = tempfile.gettempdir()
    return Environment(platform=platform, shell=shell, home=home, tmpdir=tmpdir, encoding=sys.getdefaultencoding())


class LocalKaos(Kaos):
    """
    本地环境 Kaos 实现
    参考 kimi-code LocalKaos: 独立 _cwd + 不可变切换
    """

    def __init__(self, os_env: Environment, cwd: str, env_overrides: Optional[Dict[str, str]] = None):
        self._os_env = os_env
        self._cwd = os.path.abspath(cwd)
        self._env_overrides = env_overrides or {}

    @classmethod
    async def create(cls, cwd: Optional[str] = None) -> "LocalKaos":
        os_env = _detect_environment()
        if cwd is None:
            cwd = os.getcwd()
        return cls(os_env, cwd)

    @property
    def name(self) -> str:
        return "local"

    @property
    def os_env(self) -> Environment:
        return self._os_env

    def path_class(self) -> str:
        return "win32" if self._os_env.platform == "win32" else "posix"

    def normpath(self, path: str) -> str:
        return os.path.normpath(self._resolve_path(path))

    def get_home(self) -> str:
        return self._os_env.home

    def get_cwd(self) -> str:
        return self._cwd

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(self._cwd, path))

    async def chdir(self, path: str) -> None:
        resolved = os.path.abspath(self._resolve_path(path))
        if not os.path.isdir(resolved):
            raise KaosFileNotFoundError(f"目录不存在: {resolved}")
        self._cwd = resolved

    def with_cwd(self, cwd: str) -> "LocalKaos":
        resolved = os.path.abspath(self._resolve_path(cwd))
        return LocalKaos(os_env=self._os_env, cwd=resolved, env_overrides=dict(self._env_overrides))

    def with_env(self, env: Dict[str, str]) -> "LocalKaos":
        merged = dict(self._env_overrides)
        merged.update(env)
        return LocalKaos(os_env=self._os_env, cwd=self._cwd, env_overrides=merged)

    async def stat(self, path: str, follow_symlinks: bool = True) -> StatResult:
        resolved = self._resolve_path(path)
        try:
            return StatResult.from_os_stat(resolved)
        except FileNotFoundError:
            raise KaosFileNotFoundError(f"文件不存在: {resolved}")
        except PermissionError:
            raise KaosPermissionError(f"权限不足: {resolved}")

    async def iterdir(self, path: str) -> AsyncGenerator[str, None]:
        resolved = self._resolve_path(path)
        if not os.path.isdir(resolved):
            raise KaosFileNotFoundError(f"目录不存在: {resolved}")
        try:
            for entry in os.listdir(resolved):
                yield entry
        except PermissionError:
            raise KaosPermissionError(f"权限不足: {resolved}")

    async def glob(self, path: str, pattern: str) -> AsyncGenerator[str, None]:
        resolved = self._resolve_path(path)
        base = resolved
        if "**" in pattern:
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in dirs + files:
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, base)
                    if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
                        yield rel
        else:
            full_pattern = os.path.join(base, pattern)
            for match in glob_module.glob(full_pattern):
                yield os.path.relpath(match, base)

    async def read_bytes(self, path: str) -> bytes:
        resolved = self._resolve_path(path)
        try:
            with open(resolved, "rb") as f:
                return f.read()
        except FileNotFoundError:
            raise KaosFileNotFoundError(f"文件不存在: {resolved}")

    async def read_text(self, path: str, encoding: str = "utf-8", errors: str = "replace") -> str:
        resolved = self._resolve_path(path)
        try:
            with open(resolved, "r", encoding=encoding, errors=errors) as f:
                return f.read()
        except FileNotFoundError:
            raise KaosFileNotFoundError(f"文件不存在: {resolved}")

    async def read_lines(self, path: str, encoding: str = "utf-8") -> AsyncGenerator[str, None]:
        resolved = self._resolve_path(path)
        try:
            with open(resolved, "r", encoding=encoding) as f:
                for line in f:
                    yield line.rstrip("\n\r")
        except FileNotFoundError:
            raise KaosFileNotFoundError(f"文件不存在: {resolved}")

    async def write_bytes(self, path: str, data: bytes) -> int:
        resolved = self._resolve_path(path)
        os.makedirs(os.path.dirname(resolved) or ".", exist_ok=True)
        with open(resolved, "wb") as f:
            return f.write(data)

    async def write_text(self, path: str, data: str, encoding: str = "utf-8", mode: str = "w") -> int:
        resolved = self._resolve_path(path)
        os.makedirs(os.path.dirname(resolved) or ".", exist_ok=True)
        with open(resolved, mode, encoding=encoding) as f:
            return f.write(data)

    async def mkdir(self, path: str, parents: bool = True, exist_ok: bool = True) -> None:
        resolved = self._resolve_path(path)
        if os.path.exists(resolved):
            if not exist_ok:
                raise KaosFileExistsError(f"目录已存在: {resolved}")
            if not os.path.isdir(resolved):
                raise KaosError(f"路径已存在但不是目录: {resolved}")
            return
        try:
            if parents:
                os.makedirs(resolved)
            else:
                os.mkdir(resolved)
        except PermissionError:
            raise KaosPermissionError(f"权限不足: {resolved}")

    async def exec(self, *args: str) -> KaosProcess:
        return await self._run(args=list(args))

    async def exec_with_env(self, args: List[str], env: Optional[Dict[str, str]] = None) -> KaosProcess:
        merged_env = dict(self._env_overrides)
        if env:
            merged_env.update(env)
        return await self._run(args=args, extra_env=merged_env)

    async def _run(self, args: List[str], extra_env: Optional[Dict[str, str]] = None) -> KaosProcess:
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd, env=env,
            )
            stdout, stderr = await proc.communicate()
            return KaosProcess(
                pid=proc.pid, returncode=proc.returncode,
                stdout=stdout.decode(self._os_env.encoding, errors="replace"),
                stderr=stderr.decode(self._os_env.encoding, errors="replace"),
                _process=proc,
            )
        except FileNotFoundError:
            raise KaosError(f"命令未找到: {args[0]}")
