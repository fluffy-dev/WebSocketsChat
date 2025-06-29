import asyncio
import websockets
import json
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO)

# Используем defaultdict для удобства. Если комнаты еще нет, она будет создана с пустым set.
# Структура: {"room_name": {websocket1, websocket2, ...}}
ROOMS = defaultdict(set)
# Словарь для хранения метаданных о клиенте (никнейм)
# Структура: {websocket: "username"}
CLIENTS_METADATA = {}


async def broadcast(room_name, message):
    """
    Рассылает сообщение всем клиентам в указанной комнате.
    """
    if room_name in ROOMS:
        # Создаем копию множества, чтобы избежать проблем при его изменении во время итерации
        clients_in_room = ROOMS[room_name].copy()
        tasks = [client.send(message) for client in clients_in_room]
        if tasks:
            await asyncio.gather(*tasks)


async def handler(websocket):
    """
    Основной обработчик подключений.
    """
    logging.info(f"Новое подключение от {websocket.remote_address}")

    room_name = None
    username = None

    try:
        # 1. Ожидаем первое сообщение для авторизации
        join_message_str = await websocket.recv()
        join_data = json.loads(join_message_str)

        # Проверяем, что это сообщение о входе
        if join_data.get("type") == "join":
            room_name = join_data["payload"]["room"]
            username = join_data["payload"]["username"]

            # Регистрируем клиента
            ROOMS[room_name].add(websocket)
            CLIENTS_METADATA[websocket] = username

            logging.info(f"Пользователь '{username}' вошел в комнату '{room_name}'.")

            # 2. Уведомляем всех в комнате о новом участнике
            notification = json.dumps({
                "type": "user_joined",
                "payload": {"username": username}
            })
            await broadcast(room_name, notification)

        else:
            # Если первое сообщение не "join", закрываем соединение
            logging.warning(f"Соединение закрыто: первое сообщение не 'join'.")
            await websocket.close(code=1008, reason="Join message required")
            return

        # 3. Основной цикл прослушивания сообщений чата
        async for message_str in websocket:
            message_data = json.loads(message_str)

            if message_data.get("type") == "chat":
                chat_text = message_data["payload"]["message"]
                logging.info(f"[{room_name}] '{username}': {chat_text}")

                # Формируем сообщение для рассылки
                response = json.dumps({
                    "type": "chat_message",
                    "payload": {
                        "username": username,
                        "message": chat_text
                    }
                })
                await broadcast(room_name, response)

    except websockets.exceptions.ConnectionClosed as e:
        logging.info(f"Соединение с {websocket.remote_address} закрыто: {e}")
    finally:
        # 4. Отменяем регистрацию клиента при отключении
        if room_name and websocket in ROOMS[room_name]:
            ROOMS[room_name].remove(websocket)
            del CLIENTS_METADATA[websocket]

            logging.info(f"Пользователь '{username}' покинул комнату '{room_name}'.")

            # Уведомляем оставшихся участников о выходе
            notification = json.dumps({
                "type": "user_left",
                "payload": {"username": username}
            })
            await broadcast(room_name, notification)

            # Если комната опустела, удаляем ее
            if not ROOMS[room_name]:
                del ROOMS[room_name]
                logging.info(f"Комната '{room_name}' пуста и удалена.")


async def main():
    async with websockets.serve(handler, "localhost", 8765):
        logging.info("WebSocket сервер запущен на ws://localhost:8765")
        await asyncio.Future()  # работать вечно


if __name__ == "__main__":
    asyncio.run(main())