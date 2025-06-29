import asyncio
import json
import logging
from typing import Dict

from pydantic import ValidationError
from websockets.legacy.server import WebSocketServerProtocol

from client import Client
from models import (ClientChatPayload, ClientJoinPayload,
                    ChatMessagePayload, MessageType, ServerMessage,
                    UserInfoPayload, ErrorPayload)
from room import Room


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
