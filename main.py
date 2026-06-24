import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command

from config import BOT_TOKEN
from db.database import init_db
from handlers.clan import router as clan_router
from handlers.duel import router as duel_router
from handlers.scheduler import war_scheduler, save_group_chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Сначала подключаем роутеры — их хендлеры будут проверяться первыми
dp.include_router(clan_router)
dp.include_router(duel_router)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type in ("group", "supergroup"):
        await save_group_chat(message.chat.id)

    await message.answer(
        "⚔️ <b>Бот Войны Кланов</b>\n\n"
        "Команды:\n"
        "/createclan — создать клан\n"
        "/join — вступить в клан\n"
        "/clan — профиль своего клана\n"
        "/top — таблица кланов\n"
        "/leaveclan — выйти из клана\n"
        "/kick — кикнуть участника (лидер)\n"
        "/transferlead — передать лидерство\n"
        "/minduel — начать игру (когда вызван на дуэль)",
        parse_mode="HTML"
    )


# Этот хендлер должен быть ПОСЛЕДНИМ — ловит только обычные сообщения, не команды
@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.startswith("/") == False)
async def track_group(message: Message):
    """Запоминаем ID группы из любого сообщения."""
    await save_group_chat(message.chat.id)


async def set_commands():
    commands = [
        BotCommand(command="start", description="Начало работы"),
        BotCommand(command="createclan", description="Создать клан"),
        BotCommand(command="join", description="Вступить в клан"),
        BotCommand(command="clan", description="Профиль клана"),
        BotCommand(command="top", description="Таблица кланов"),
        BotCommand(command="leaveclan", description="Выйти из клана"),
        BotCommand(command="kick", description="Кикнуть участника"),
        BotCommand(command="transferlead", description="Передать лидерство"),
        BotCommand(command="minduel", description="Начать дуэль-игру"),
    ]
    await bot.set_my_commands(commands)


async def main():
    await init_db()
    await set_commands()
    logger.info("Бот запускается...")

    # Запускаем планировщик дуэлей в фоне
    asyncio.create_task(war_scheduler(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
