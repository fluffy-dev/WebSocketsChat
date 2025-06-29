import asyncio
import json
import logging
import uuid
from typing import Dict

import websockets
from pydantic import ValidationError
from websockets.legacy.server import WebSocketServerProtocol

from models import (BaseMessage, ClientChatPayload, ClientJoinPayload,
                    ChatMessagePayload, MessageType, ServerMessage,
                    UserInfoPayload, ErrorPayload)

logging.basicConfig(level=logging.INFO)


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


class ConnectionManager:
    """
    Управляет всеми активными соединениями, комнатами и клиентами.
    """

    def __init__(self):
        """Инициализирует менеджер с пустым списком комнат."""
        self._rooms: Dict[str, Room] = {}

    def _get_or_create_room(self, room_name: str) -> Room:
        """
        Возвращает существующую комнату или создает новую, если она не существует.

        Args:
            room_name: Название комнаты.

        Returns:
            Экземпляр класса Room.
        """
        if room_name not in self._rooms:
            self._rooms[room_name] = Room(name=room_name)
        return self._rooms[room_name]

    async def handle_connection(self, websocket: WebSocketServerProtocol):
        """
        Основной обработчик для нового WebSocket соединения.

        Args:
            websocket: Экземпляр WebSocket соединения от библиотеки websockets.
        """
        client = Client(websocket)
        logging.info(f"Новое соединение: {client.id} от {websocket.remote_address}")

        try:
            await self._handle_join_flow(client)
            await self._handle_chat_flow(client)
        except ConnectionAbortedError as e:
            logging.warning(f"Соединение {client.id} прервано во время входа: {e}")
        except Exception as e:
            logging.error(f"Неожиданная ошибка у клиента {client.id}: {e}", exc_info=True)
        finally:
            await self._disconnect(client)

    async def _handle_join_flow(self, client: Client):
        """Обрабатывает логику входа клиента в комнату."""
        try:
            raw_message = await asyncio.wait_for(client.websocket.recv(), timeout=10.0)
            data = json.loads(raw_message)

            if data.get("type") != MessageType.JOIN_ROOM.value:
                raise ValueError("Первое сообщение должно быть типа JOIN_ROOM")

            payload = ClientJoinPayload(**data.get("payload", {}))

            room = self._get_or_create_room(payload.room_name)
            client.assign_details(username=payload.username, room_name=payload.room_name)
            room.add_client(client)

            logging.info(f"Клиент {client.id} ({client.username}) присоединился к комнате '{room.name}'")

            join_notification = ServerMessage(
                type=MessageType.USER_JOINED,
                payload=UserInfoPayload(user_id=client.id, username=client.username)
            )
            await room.broadcast(join_notification)

        except (ValidationError, ValueError, json.JSONDecodeError, asyncio.TimeoutError) as e:
            error_payload = ErrorPayload(detail=f"Ошибка входа: {e}")
            error_message = ServerMessage(type=MessageType.ERROR, payload=error_payload)
            await client.send(error_message)
            raise ConnectionAbortedError("Не удалось выполнить вход в комнату.") from e

    async def _handle_chat_flow(self, client: Client):
        """Обрабатывает получение и рассылку сообщений в чате."""
        room = self._rooms[client.room_name]
        async for raw_message in client.websocket:
            try:
                data = json.loads(raw_message)
                if data.get("type") != MessageType.CHAT_MESSAGE.value:
                    continue

                payload = ClientChatPayload(**data.get("payload", {}))

                chat_message = ServerMessage(
                    type=MessageType.CHAT_MESSAGE,
                    payload=ChatMessagePayload(
                        user_id=client.id,
                        username=client.username,
                        message_text=payload.message_text
                    )
                )
                await room.broadcast(chat_message)

            except (ValidationError, json.JSONDecodeError) as e:
                logging.warning(f"Ошибка валидации сообщения от {client.id}: {e}")

    async def _disconnect(self, client: Client):
        """
        Обрабатывает отключение клиента.

        Args:
            client: Отключаемый клиент.
        """
        if not client.room_name or client.room_name not in self._rooms:
            logging.info(f"Клиент {client.id} отключился до входа в комнату.")
            return

        room = self._rooms[client.room_name]
        room.remove_client(client.id)

        logging.info(f"Клиент {client.id} ({client.username}) покинул комнату '{room.name}'")

        leave_notification = ServerMessage(
            type=MessageType.USER_LEFT,
            payload=UserInfoPayload(user_id=client.id, username=client.username)
        )
        await room.broadcast(leave_notification)

        if room.is_empty():
            del self._rooms[room.name]
            logging.info(f"Комната '{room.name}' пуста и удалена.")


async def main():
    """Главная функция для запуска сервера."""
    manager = ConnectionManager()
    async with websockets.serve(manager.handle_connection, "localhost", 8765):
        logging.info("WebSocket сервер запущен на ws://localhost:8765")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())