"""
Разовый скрипт для определения chat_id.

Запуск:
    python scripts/tg_get_chat_id.py

Напишите боту (или любое сообщение в группу/канал, куда он добавлен) —
в консоли появится chat_id, тип чата и название. После этого используйте
этот chat_id как TG_CHAT_ID в .env.

Если это форум-группа с подтемами (topics) — напишите сообщение ИМЕННО
в нужной подтеме (не в General), тогда дополнительно появится
message_thread_id — его нужно прописать как TG_CHAT_THREAD_ID в .env,
чтобы сообщения приходили в конкретную подтему, а не в General.

Остановить — Ctrl+C.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decouple import config
from aiogram import Bot, Dispatcher
from aiogram.types import Message

TG_BOT_TOKEN = config('TG_BOT_TOKEN', default='')

if not TG_BOT_TOKEN:
    print("TG_BOT_TOKEN не найден в .env")
    sys.exit(1)

bot = Bot(token=TG_BOT_TOKEN)
dp = Dispatcher()


@dp.message()
async def echo_chat_id(message: Message):
    chat = message.chat
    thread_id = message.message_thread_id
    print(
        f"\nchat_id: {chat.id}\n"
        f"тип: {chat.type}\n"
        f"название/имя: {chat.title or chat.full_name}\n"
        f"message_thread_id (подтема/топик): {thread_id if thread_id else '— (это General/обычный чат)'}\n"
    )
    reply = f"chat_id: {chat.id}"
    if thread_id:
        reply += f"\nmessage_thread_id: {thread_id}"
    await message.answer(reply)
    dp.stop_polling()


async def main():
    print(f"Бот запущен, жду сообщение... (Ctrl+C для остановки)")
    me = await bot.get_me()
    print(f"Это бот @{me.username}")
    await dp.start_polling(bot)
    print("Сообщение получено, остановка.")


if __name__ == '__main__':
    asyncio.run(main())
