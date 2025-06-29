import asyncio
import logging
import websockets

from connection_manager import ConnectionManager

logging.basicConfig(level=logging.INFO)


async def main():
    """Главная функция для запуска сервера."""
    manager = ConnectionManager()
    async with websockets.serve(manager.handle_connection, "localhost", 8765):
        logging.info("WebSocket сервер запущен на ws://localhost:8765")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())