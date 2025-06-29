import asyncio
import uuid
from typing import Dict

from client import Client
from models import BaseMessage


class Room:
    """
    Представляет чат-комнату, управляющую набором клиентов.

    Attributes:
        name (str): Название комнаты.
    """

    def __init__(self, name: str):
        """Инициализирует комнату с заданным именем."""
        self.name = name
        self._clients: Dict[uuid.UUID, Client] = {}

    def add_client(self, client: Client):
        """Добавляет клиента в комнату."""
        self._clients[client.id] = client

    def remove_client(self, client_id: uuid.UUID):
        """Удаляет клиента из комнаты."""
        if client_id in self._clients:
            del self._clients[client_id]

    async def broadcast(self, message: BaseMessage):
        """
        Рассылает сообщение абсолютно всем клиентам в комнате.

        Args:
            message: Сообщение для рассылки.
        """
        tasks = [client.send(message) for client in self._clients.values()]
        if tasks:
            await asyncio.gather(*tasks)

    def is_empty(self) -> bool:
        """Проверяет, пуста ли комната."""
        return not self._clients

