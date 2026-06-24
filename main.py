import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
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


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("❌ Действие отменено.")
    else:
        await message.answer("Нечего отменять.")


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
        BotCommand(command="cancel", description="Отменить действие"),
        BotCommand(command="deleteclan", description="Удалить клан (лидер)"),
        BotCommand(command="reset", description="Сбросить зависшую игру"),
    ]
    await bot.set_my_commands(commands)


async def main():
    await init_db()
    await set_commands()
    logger.info("Бот запускается...")

    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(war_scheduler(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
