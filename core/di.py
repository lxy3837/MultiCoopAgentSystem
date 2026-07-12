"""
DI 容器 - 参考 kimi-code InstantiationService + ServiceCollection 设计

核心概念:
- ServiceIdentifier: 服务标识符（用字符串做 key）
- ServiceCollection: 服务注册表 {id: instance_or_factory}
- ServiceContainer: 容器，支持延迟实例化 + 依赖注入 + 单例管理
"""
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, Type, TypeVar
from utils.logger import get_logger

T = TypeVar("T")


class CyclicDependencyError(Exception):
    """循环依赖错误"""
    pass


class ServiceNotFoundError(Exception):
    """服务未注册"""
    pass


class ServiceCollection:
    """
    服务注册表
    参考 kimi-code ServiceCollection: Map<ServiceIdentifier, instance | descriptor>
    """

    def __init__(self, **entries):
        self._entries: Dict[str, Any] = {}
        for key, value in entries.items():
            self.set(key, value)

    def set(self, key: str, instance_or_factory: Any):
        """注册服务（实例或工厂函数）"""
        self._entries[key] = instance_or_factory

    def get(self, key: str) -> Any:
        """获取服务"""
        if key not in self._entries:
            raise ServiceNotFoundError(f"服务未注册: {key}")
        return self._entries[key]

    def has(self, key: str) -> bool:
        return key in self._entries

    def keys(self):
        return self._entries.keys()

    def items(self):
        return self._entries.items()


class ServiceContainer:
    """
    DI 容器
    参考 kimi-code InstantiationService:
    - 支持单例（singleton）
    - 支持工厂延迟实例化
    - 依赖注入（通过 factory 函数接收容器引用）
    - 循环依赖检测
    """

    def __init__(self, collection: ServiceCollection = None):
        self._services: ServiceCollection = collection or ServiceCollection()
        self._instances: Dict[str, Any] = {}  # 已实例化的单例缓存
        self._resolving: set[str] = set()  # 正在解析的服务（循环检测）
        self._singletons: set[str] = set()  # 标记为单例的服务
        self.logger = get_logger("di")

    def register(self, key: str, factory: Callable[["ServiceContainer"], Any], singleton: bool = True):
        """
        注册服务
        参考 kimi-code ServiceCollection.set(id, SyncDescriptor)
        """
        self._services.set(key, factory)
        if singleton:
            self._singletons.add(key)

    def register_instance(self, key: str, instance: Any):
        """直接注册已有实例"""
        self._services.set(key, instance)
        self._instances[key] = instance
        self._singletons.add(key)

    def get(self, key: str) -> Any:
        """
        获取服务（自动解析依赖、处理单例）
        参考 kimi-code _createAndCacheServiceInstance
        """
        # 已缓存
        if key in self._instances:
            return self._instances[key]

        # 循环依赖检测
        if key in self._resolving:
            raise CyclicDependencyError(f"检测到循环依赖: {key}")

        value = self._services.get(key)

        # 直接实例（已注册的实例）
        if not callable(value):
            self._instances[key] = value
            return value

        # 工厂函数
        self._resolving.add(key)
        try:
            instance = value(self)
            if key in self._singletons:
                self._instances[key] = instance
            return instance
        finally:
            self._resolving.discard(key)

    def get_typed(self, key: str, expected_type: Type[T]) -> T:
        """类型安全的获取"""
        instance = self.get(key)
        if not isinstance(instance, expected_type):
            raise TypeError(f"服务 {key} 类型不匹配: 期望 {expected_type}, 实际 {type(instance)}")
        return instance

    def create_child(self, extra_services: Dict[str, Any] = None) -> "ServiceContainer":
        """
        创建子容器（参考 kimi-code createChild）
        子容器继承父容器所有注册，但有自己的实例缓存
        """
        child_collection = ServiceCollection(**dict(self._services.items()))
        if extra_services:
            for k, v in extra_services.items():
                child_collection.set(k, v)

        child = ServiceContainer(child_collection)
        child._singletons = set(self._singletons)
        return child

    def dispose(self):
        """释放所有资源"""
        self._instances.clear()
        self._resolving.clear()
        self.logger.info("DI 容器已释放")

    @property
    def registered_services(self) -> list:
        return list(self._services.keys())
