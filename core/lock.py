"""
Server 锁机制 - 参考 kimi-code server/lock.ts
基于文件的进程互斥锁，支持过期检测和回收

设计（参考 kimi-code LockManager）:
- 排他创建：os.open(O_CREAT | O_EXCL) 保证原子性
- PID 存活检测：os.kill(pid, 0) 探测进程是否存在
- 过期接管：锁存在但 PID 已死 → 继承锁
- 竞态防御：接管时重新 O_EXCL 创建
- 所有权保护：release() 前检查 PID 匹配
"""
from __future__ import annotations
import os
import sys
import json
import time
import errno
from dataclasses import dataclass, asdict
from typing import Optional
from utils.logger import get_logger


@dataclass
class LockInfo:
    """锁文件内容"""
    pid: int
    started_at: float
    port: int = 0
    host: str = "127.0.0.1"
    host_version: str = "1.0.0"
    entry: str = ""


class ServerLockError(Exception):
    """服务器锁异常"""
    def __init__(self, message: str, code: str = "LOCK_ERROR", existing: Optional[LockInfo] = None):
        super().__init__(message)
        self.code = code
        self.existing = existing


class ServerLockedError(ServerLockError):
    """服务器已被其他进程锁定"""
    pass


class ServerLockManager:
    """
    文件锁管理器
    参考 kimi-code LockManager:
    - acquire() → 尝试获取锁
    - release() → 释放锁（检查所有权）
    - update() → 更新锁文件内容
    """

    def __init__(self, lock_dir: str = None):
        if lock_dir is None:
            lock_dir = os.path.join(os.path.expanduser("~"), ".mcasys", "server")
        self.lock_dir = lock_dir
        self.lock_path = os.path.join(lock_dir, "lock")
        self.logger = get_logger("lock")
        self._acquired = False

    def acquire(self, port: int = 8000, host: str = "127.0.0.1", host_version: str = "2.0.0") -> LockInfo:
        """
        尝试获取锁
        参考 kimi-code tryExclusiveCreate + pidAlive 逻辑
        """
        os.makedirs(self.lock_dir, exist_ok=True)

        while True:
            try:
                # 原子排他创建（参考 openSync(path, 'wx')）
                fd = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            except OSError as e:
                if e.errno == errno.EEXIST:
                    # 锁已存在，检查是否过期
                    existing = self._read_lock()
                    if existing is None:
                        # 文件损坏，删除后重试
                        self._force_unlock()
                        continue

                    if self._pid_alive(existing.pid):
                        raise ServerLockedError(
                            f"服务器已被进程 PID={existing.pid} 锁定",
                            code="SERVER_LOCKED",
                            existing=existing,
                        )

                    # PID 已死，接管锁（参考 kimi-code unlink + retry）
                    self.logger.warning(
                        f"检测到僵尸锁 PID={existing.pid}（进程已死），正在继承..."
                    )
                    self._force_unlock()
                    continue
                else:
                    raise ServerLockError(f"无法创建锁文件: {e}")

            # 写入锁信息
            lock_info = LockInfo(
                pid=os.getpid(),
                started_at=time.time(),
                port=port,
                host=host,
                host_version=host_version,
                entry=f"{host}:{port}",
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(asdict(lock_info), f)
            except Exception:
                os.close(fd)
                self._force_unlock()
                raise

            self._acquired = True
            self.logger.info(f"服务器锁定成功: PID={lock_info.pid}, port={port}")
            return lock_info

    def release(self):
        """释放锁（检查所有权）"""
        if not self._acquired:
            return

        existing = self._read_lock()
        if existing and existing.pid != os.getpid():
            self.logger.warning(
                f"锁文件 PID={existing.pid} 不属于当前进程 PID={os.getpid()}，跳过释放"
            )
            return

        self._force_unlock()
        self._acquired = False
        self.logger.info("服务器锁已释放")

    def update(self, **kwargs):
        """更新锁文件内容（如更新端口号）"""
        if not self._acquired:
            return

        existing = self._read_lock()
        if existing is None:
            return

        for k, v in kwargs.items():
            if hasattr(existing, k) and v is not None:
                setattr(existing, k, v)

        with open(self.lock_path, "w") as f:
            json.dump(asdict(existing), f)

    def get_lock_info(self) -> Optional[LockInfo]:
        """读取当前锁信息"""
        return self._read_lock()

    def _read_lock(self) -> Optional[LockInfo]:
        """读取锁文件内容"""
        try:
            with open(self.lock_path, "r") as f:
                data = json.load(f)
            return LockInfo(**data)
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return None

    def _force_unlock(self):
        """强制删除锁文件"""
        try:
            os.remove(self.lock_path)
        except FileNotFoundError:
            pass

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """
        检测进程是否存活
        参考 kimi-code pidAlive: process.kill(pid, 0) → sig=0 只探测不发送信号
        """
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
