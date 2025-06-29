import logging
import logging
import uuid

import websockets
from websockets.legacy.server import WebSocketServerProtocol

from models import BaseMessage


class Client:
    """
    Представляет подключенного клиента (пользователя).

    Attributes:
        id (uuid.UUID): Уникальный идентификатор клиента.
        username (str): Имя пользователя, выбранное при входе.
        websocket (WebSocketServerProtocol): Активное WebSocket соединение.
        room_name (str): Название комнаты, к которой подключен клиент.
    """

    def __init__(self, websocket: WebSocketServerProtocol):
        """Инициализирует клиента с уникальным ID и WebSocket соединением."""
        self.id: uuid.UUID = uuid.uuid4()
        self.websocket: WebSocketServerProtocol = websocket
        self.username: str | None = None
        self.room_name: str | None = None

    async def send(self, message: BaseMessage):
        """
        Отправляет Pydantic модель клиенту в виде JSON.

        Args:
            message: Объект Pydantic, который необходимо отправить.
        """
        try:
            await self.websocket.send(message.model_dump_json())
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"Не удалось отправить сообщение клиенту {self.id}: соединение закрыто.")

    def assign_details(self, username: str, room_name: str):
        """
        Присваивает клиенту имя пользователя и название комнаты после успешного входа.

        Args:
            username: Имя пользователя.
            room_name: Название комнаты.
        """
        self.username = username
        self.room_name = room_name
