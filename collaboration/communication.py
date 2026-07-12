# collaboration/communication.py
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from utils.logger import get_logger


@dataclass
class Message:
    """
    消息数据模型：标准化Agent间通信的消息格式
    """
    message_id: str  # 消息唯一标识符
    sender_id: str   # 发送者Agent ID
    receiver_id: str # 接收者Agent ID (或 "broadcast" 表示广播)
    message_type: str  # 消息类型：task_assignment, task_completed, resource_request, etc.
    content: Dict[str, Any]     # 消息内容
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = field(default=0)  # 消息优先级：0-低, 1-中, 2-高
    status: str = field(default="pending")  # 消息状态：pending, delivered, processed


class MessageQueue:
    """
    消息队列：实现Agent间的异步通信机制
    """
    def __init__(self):
        self.queue: Dict[str, List[Message]] = {}  # 按接收者ID分组存储消息
        self.logger = get_logger("message_queue")
        self.delivered_messages: Dict[str, Message] = {}  # 已投递的消息

    def send_message(self, message: Message) -> str:
        """
        发送消息到队列
        """
        # 将消息添加到对应接收者ID的分组中
        if message.receiver_id not in self.queue:
            self.queue[message.receiver_id] = []
        self.queue[message.receiver_id].append(message)
        self.logger.debug(f"消息已发送：{message.message_id} (发送者: {message.sender_id}, 接收者: {message.receiver_id})")
        return message.message_id

    def get_message(self, agent_id: str) -> Optional[Message]:
        """
        获取指定Agent的下一条消息（优先处理高优先级消息）
        """
        # 收集目标为该Agent或广播的消息
        all_target_messages = []
        
        # 获取直接发送给该Agent的消息
        if agent_id in self.queue:
            all_target_messages.extend(self.queue[agent_id])
        
        # 获取广播消息
        if "broadcast" in self.queue:
            all_target_messages.extend(self.queue["broadcast"])
        
        if not all_target_messages:
            return None

        # 按优先级和时间排序
        all_target_messages.sort(key=lambda x: (-x.priority, x.timestamp))
        
        # 获取第一条消息
        message = all_target_messages[0]
        
        # 从对应的队列中移除该消息
        if message.receiver_id == agent_id:
            self.queue[agent_id].remove(message)
            # 如果该队列空了，移除该键
            if not self.queue[agent_id]:
                del self.queue[agent_id]
        else:  # 广播消息
            self.queue["broadcast"].remove(message)
            # 如果广播队列空了，移除该键
            if not self.queue["broadcast"]:
                del self.queue["broadcast"]
        
        # 更新消息状态为已投递
        message.status = "delivered"
        self.delivered_messages[message.message_id] = message
        
        self.logger.debug(f"消息已投递：{message.message_id} 给 Agent {agent_id}")
        return message

    def broadcast_message(self, sender_id: str, message_type: str, content: Dict[str, Any], priority: int = 0) -> str:
        """
        广播消息给所有Agent
        """
        from uuid import uuid4
        message = Message(
            message_id=str(uuid4()),
            sender_id=sender_id,
            receiver_id="broadcast",
            message_type=message_type,
            content=content,
            priority=priority
        )
        return self.send_message(message)

    def mark_message_processed(self, message_id: str) -> bool:
        """
        标记消息为已处理
        """
        if message_id in self.delivered_messages:
            self.delivered_messages[message_id].status = "processed"
            self.logger.debug(f"消息已处理：{message_id}")
            return True
        return False

    def get_pending_messages_count(self, agent_id: str) -> int:
        """
        获取指定Agent的待处理消息数量
        """
        count = 0
        # 计算直接发送给该Agent的消息数量
        if agent_id in self.queue:
            count += len(self.queue[agent_id])
        # 计算广播消息数量
        if "broadcast" in self.queue:
            count += len(self.queue["broadcast"])
        return count


class CommunicationManager:
    """
    通信管理器：管理Agent间的通信，提供发送、接收和广播消息的接口
    """
    def __init__(self):
        self.message_queue = MessageQueue()
        self.logger = get_logger("communication_manager")
        self.agent_handlers: Dict[str, Callable[[Message], None]] = {}  # Agent消息处理器映射

    def register_agent_handler(self, agent_id: str, handler: Callable[[Message], None]):
        """
        注册Agent的消息处理器
        """
        self.agent_handlers[agent_id] = handler
        self.logger.info(f"Agent {agent_id} 的消息处理器已注册")

    def unregister_agent_handler(self, agent_id: str):
        """
        注销Agent的消息处理器
        """
        if agent_id in self.agent_handlers:
            del self.agent_handlers[agent_id]
            self.logger.info(f"Agent {agent_id} 的消息处理器已注销")

    def send_message(self, message: Message) -> str:
        """
        发送消息
        """
        return self.message_queue.send_message(message)

    def broadcast_message(self, sender_id: str, message_type: str, content: Dict, priority: int = 0) -> str:
        """
        广播消息
        """
        return self.message_queue.broadcast_message(sender_id, message_type, content, priority)

    def process_messages(self):
        """
        处理所有待处理消息：分发给对应的Agent处理器
        """
        for agent_id, handler in self.agent_handlers.items():
            while True:
                message = self.message_queue.get_message(agent_id)
                if not message:
                    break
                
                try:
                    # 调用Agent的消息处理器
                    handler(message)
                    # 标记消息为已处理
                    self.message_queue.mark_message_processed(message.message_id)
                except Exception as e:
                    self.logger.error(f"处理消息 {message.message_id} 失败：{e}")

    def get_communication_stats(self) -> Dict[str, Any]:
        """
        获取通信统计信息
        """
        # 计算待处理消息总数
        pending_count = 0
        for messages in self.message_queue.queue.values():
            pending_count += len(messages)
        
        # 计算已投递和已处理消息数量
        delivered_count = 0
        processed_count = 0
        for msg in self.message_queue.delivered_messages.values():
            if msg.status == "delivered":
                delivered_count += 1
            elif msg.status == "processed":
                processed_count += 1
        
        return {
            "total_messages": pending_count + len(self.message_queue.delivered_messages),
            "pending_messages": pending_count,
            "delivered_messages": delivered_count,
            "processed_messages": processed_count
        }


# 导出核心类
__all__ = ["Message", "MessageQueue", "CommunicationManager"]