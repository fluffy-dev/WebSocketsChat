from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field

class MessageType(str, Enum):
    """
    Перечисление типов сообщений, которыми обмениваются клиент и сервер.
    """
    JOIN_ROOM = "join_room"
    CHAT_MESSAGE = "chat_message"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    ERROR = "error"

# --- Модели для сообщений, отправляемых клиентом ---

class ClientJoinPayload(BaseModel):
    """Полезная нагрузка для события входа в комнату."""
    username: str = Field(..., min_length=1, max_length=50)
    room_name: str = Field(..., min_length=1, max_length=50)

class ClientChatPayload(BaseModel):
    """Полезная нагрузка для отправки сообщения в чат."""
    message_text: str = Field(..., min_length=1, max_length=1000)

# --- Модели для сообщений, отправляемых сервером ---

class BaseServerPayload(BaseModel):
    """Базовая модель для всех полезных нагрузок от сервера."""
    pass

class UserInfoPayload(BaseServerPayload):
    """Информация о пользователе, который присоединился или покинул чат."""
    user_id: UUID
    username: str

class ChatMessagePayload(UserInfoPayload):
    """Полезная нагрузка для сообщения в чате, отправленного сервером."""
    message_text: str

class ErrorPayload(BaseServerPayload):
    """Полезная нагрузка для сообщения об ошибке."""
    detail: str

# --- Основные структуры сообщений ---

class BaseMessage(BaseModel):
    """Базовая модель для любого сообщения."""
    type: MessageType

class ServerMessage(BaseMessage):
    """
    Модель сообщения, отправляемого сервером клиенту.
    """
    payload: UserInfoPayload | ChatMessagePayload | ErrorPayload