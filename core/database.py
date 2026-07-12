"""
数据库管理层 - SQLAlchemy + aiosqlite
提供异步、并发安全的数据库访问，替代原来的 JSON 文件存储。
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class DatabaseManager:
    """异步数据库管理器（单例）"""

    _instance = None

    def __new__(cls, db_path: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = None):
        if self._initialized:
            return
        if db_path is None:
            db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_storage")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "mcasys.db")
        self._db_path = db_path
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._initialized = True

    @property
    def session_factory(self):
        return self._session_factory

    @property
    def engine(self):
        return self._engine

    async def create_tables(self):
        """创建所有表"""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        """关闭数据库连接"""
        await self._engine.dispose()


async def init_db(db_path: str = None):
    """初始化数据库：创建引擎、建表"""
    db = DatabaseManager(db_path)
    await db.create_tables()
    return db


async def get_db() -> AsyncSession:
    """获取数据库会话（依赖注入用）"""
    db = DatabaseManager()
    async with db.session_factory() as session:
        yield session
