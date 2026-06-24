import json
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from db.clan_queries import (
    get_clan_by_id, get_user_clan, update_clan_al,
    update_clan_stats_win, update_clan_stats_loss, get_active_war
)
from db.duel_queries import (
    get_duel, get_active_duel_for_user, create_session,
    get_active_session_for_user, update_session,
    mark_player_done, decrement_attempts, get_next_player,
    set_duel_status, add_to_queue, get_queue
)
from game.mines import (
    generate_field, get_current_multiplier, get_next_multipliers_str,
    get_full_progression_str, open_cell, calc_new_al,
    build_field_buttons, mines_choice_keyboard
)
from config import MULTIPLIERS, LOSE_MULTIPLIER

router = Router()


def _rules_text(clan_al: int, mines: int = None) -> str:
    lose_al = max(int(clan_al * LOSE_MULTIPLIER), 10)
    rules = (
        "📋 <b>Правила дуэли:</b>\n"
        "• Каждый игрок получает своё поле 5×5\n"
        "• Открывай клетки — находи 💎, избегай 💣\n"
        f"• При попадании на мину: очки клана ×{LOSE_MULTIPLIER} "
        f"(сейчас {clan_al} Al → станет {lose_al} Al)\n"
        "• Можно забрать выигрыш в любой момент кнопкой ✅\n"
        "• Чем больше мин выбрал — тем выше прогрессия множителей"
    )
    return rules


def _progressions_text() -> str:
    lines = ["📊 <b>Прогрессия множителей:</b>\n"]
    for m in range(1, 7):
        prog = get_full_progression_str(m)
        lines.append(f"{'💣' * m} <b>{m} мин{'а' if m==1 else 'ы' if m<5 else ''}:</b>\n{prog}")
    return "\n".join(lines)


async def announce_duel(bot: Bot, chat_id: int, duel_id: int,
                        clan1: dict, clan2: dict, player1_id: int, player2_id: int):
    """Отправляет объявление о дуэли в групповой чат."""
    p1_mention = f'<a href="tg://user?id={player1_id}">воин клана {clan1["name"]}</a>'
    p2_mention = f'<a href="tg://user?id={player2_id}">воин клана {clan2["name"]}</a>'

    text = (
        "⚔️ <b>ВЫЗОВ НА ДУЭЛЬ!</b> ⚔️\n\n"
        f"🛡 {p1_mention}\n"
        f"🗡 против\n"
        f"🛡 {p2_mention}\n\n"
        f"Честь и слава ваших кланов на кону!\n\n"
        f"💠 <b>{clan1['name']}</b>: {clan1['al']} Al\n"
        f"💠 <b>{clan2['name']}</b>: {clan2['al']} Al\n\n"
        f"Напишите в <b>личку боту</b> команду:\n"
        f"/minduel — чтобы начать игру"
    )
    msg = await bot.send_message(chat_id, text, parse_mode="HTML")
    return msg.message_id


@router.message(Command("minduel"))
async def cmd_minduel(message: Message):
    user_id = message.from_user.id
    clan = await get_user_clan(user_id)
    if not clan:
        await message.answer("⚠️ Ты не состоишь ни в одном клане.")
        return

    duel = await get_active_duel_for_user(user_id)
    if not duel:
        await message.answer("⏳ Сейчас нет активной дуэли для тебя.")
        return

    # Проверяем, не сыграл ли уже в этой дуэли
    player_num = 1 if duel["player1_id"] == user_id else 2
    done_col = f"player{player_num}_done"
    if duel.get(done_col) == 1:
        await message.answer("✅ Ты уже сыграл в этой дуэли. Жди следующей!")
        return

    # Проверяем не играл ли уже
    existing = await get_active_session_for_user(user_id)
    if existing:
        await message.answer("▶️ У тебя уже есть активная игра!")
        return

    # Определяем клан соперника для показа ставок
    clan1 = await get_clan_by_id(duel["clan1_id"])
    clan2 = await get_clan_by_id(duel["clan2_id"])

    rules = _rules_text(clan["al"])
    progressions = _progressions_text()

    text = (
        f"⚔️ <b>Дуэль #{duel['id']}</b>\n"
        f"💠 Твои Al: <b>{clan['al']}</b>\n\n"
        f"<blockquote>{rules}</blockquote>\n\n"
        f"<blockquote>{progressions}</blockquote>\n\n"
        f"Выбери количество мин на поле:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=mines_choice_keyboard())
    # Сохраняем duel_id для следующего шага в FSM через callback


@router.callback_query(F.data.startswith("mines_"))
async def cb_choose_mines(call: CallbackQuery):
    mines = int(call.data.split("_")[1])
    user_id = call.from_user.id

    clan = await get_user_clan(user_id)
    if not clan:
        await call.answer("Ты не в клане!", show_alert=True)
        return

    duel = await get_active_duel_for_user(user_id)
    if not duel:
        await call.answer("Дуэль уже завершена.", show_alert=True)
        return

    existing = await get_active_session_for_user(user_id)
    if existing:
        await call.answer("У тебя уже идёт игра!", show_alert=True)
        return

    # Создаём сессию
    session_id = await create_session(duel["id"], user_id, clan["id"], call.message.chat.id)
    field = generate_field(mines)
    await update_session(
        session_id,
        mines=mines,
        field=json.dumps(field),
        opened=json.dumps([]),
        current_multiplier=1.0,
        step=0,
        status="playing",
        message_id=call.message.message_id
    )

    prog = get_full_progression_str(mines)
    text = (
        f"⚔️ <b>Дуэль #{duel['id']}</b>\n"
        f"{'💣' * mines} Мин: <b>{mines}</b>\n"
        f"💠 Ставка: <b>{clan['al']} Al</b>\n"
        f"📊 Выигрыш: x1.00 / {clan['al']} Al\n\n"
        f"🧮 <b>Прогрессия:</b>\n{prog}\n\n"
        f"Открывай клетки!"
    )
    kb = build_field_buttons(field, [])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("cell_"))
async def cb_cell(call: CallbackQuery, bot: Bot):
    data = call.data
    user_id = call.from_user.id

    if data == "cell_cashout":
        await _cashout(call, bot)
        return

    if data.startswith("cell_noop_"):
        await call.answer()
        return

    pos = int(data.split("_")[1])

    session = await get_active_session_for_user(user_id)
    if not session or session["status"] != "playing":
        await call.answer("Игра не активна.", show_alert=True)
        return

    clan = await get_user_clan(user_id)
    field = json.loads(session["field"])
    opened = json.loads(session["opened"])

    if pos in opened:
        await call.answer("Эта клетка уже открыта!")
        return

    is_mine = open_cell(field, opened, pos)
    duel = await get_duel(session["duel_id"])
    mines = session["mines"]

    if is_mine:
        # Проигрыш
        new_al = calc_new_al(clan["al"], session["current_multiplier"], won=False)
        await update_clan_al(clan["id"], new_al)
        await update_clan_stats_loss(clan["id"])
        await update_session(session["id"], status="lost", opened=json.dumps(opened))
        await _mark_done_and_check(duel, user_id, clan["id"])

        text = (
            f"💥 <b>БУМ! Ты нашёл мину!</b>\n\n"
            f"{'💣' * mines} Мин было: {mines}\n"
            f"💠 Al клана: {clan['al']} → <b>{new_al}</b>\n"
            f"📉 (×{LOSE_MULTIPLIER})\n\n"
            f"Лучше повезёт в следующий раз!"
        )
        kb = build_field_buttons(field, opened, game_over=True)
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

        # Уведомить в группу
        if duel and duel.get("chat_id"):
            uname = f"@{call.from_user.username}" if call.from_user.username else call.from_user.full_name
            await bot.send_message(
                duel["chat_id"],
                f"💥 <b>{uname}</b> ({clan['name']}) подорвался на мине!\n"
                f"Al клана: {clan['al']} → {new_al}",
                parse_mode="HTML"
            )
    else:
        # Безопасная клетка
        step = session["step"] + 1
        mult = get_current_multiplier(mines, step)
        next_prog = get_next_multipliers_str(mines, step)
        new_al_preview = int(clan["al"] * mult)

        await update_session(
            session["id"],
            opened=json.dumps(opened),
            step=step,
            current_multiplier=mult
        )

        text = (
            f"⚔️ <b>Дуэль #{duel['id']}</b>\n"
            f"{'💣' * mines} Мин: {mines}\n"
            f"💠 Ставка: {clan['al']} Al\n"
            f"📊 Выигрыш: <b>x{mult:.2f} / {new_al_preview} Al</b>\n\n"
            f"🧮 <b>Следующий множитель:</b>\n{next_prog}"
        )
        kb = build_field_buttons(field, opened)
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

    await call.answer()


async def _cashout(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    session = await get_active_session_for_user(user_id)
    if not session or session["status"] != "playing":
        await call.answer("Игра не активна.", show_alert=True)
        return

    clan = await get_user_clan(user_id)
    mult = session["current_multiplier"]
    mines = session["mines"]
    new_al = calc_new_al(clan["al"], mult, won=True)
    uname = call.from_user.username or ""

    await update_clan_al(clan["id"], new_al)
    await update_clan_stats_win(clan["id"], mult, user_id, uname)
    await update_session(session["id"], status="done")

    duel = await get_duel(session["duel_id"])
    await _mark_done_and_check(duel, user_id, clan["id"])

    field = json.loads(session["field"])
    opened = json.loads(session["opened"])

    text = (
        f"✅ <b>Выигрыш забран!</b>\n\n"
        f"{'💣' * mines} Мин: {mines}\n"
        f"📊 Множитель: x{mult:.2f}\n"
        f"💠 Al клана: {clan['al']} → <b>{new_al}</b>\n\n"
        f"Отличная игра!"
    )
    kb = build_field_buttons(field, opened, game_over=True)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

    if duel and duel.get("chat_id"):
        mention = f"@{uname}" if uname else call.from_user.full_name
        await bot.send_message(
            duel["chat_id"],
            f"✅ <b>{mention}</b> ({clan['name']}) забрал выигрыш!\n"
            f"x{mult:.2f} | Al: {clan['al']} → {new_al}",
            parse_mode="HTML"
        )
    await call.answer()


async def _mark_done_and_check(duel: dict, user_id: int, clan_id: int):
    if not duel:
        return
    player_num = 1 if duel["player1_id"] == user_id else 2
    await decrement_attempts(clan_id, user_id)
    await mark_player_done(duel["id"], player_num)

    # Проверяем, есть ли ещё игроки в очереди этого клана
    # Если да — передаём попытку следующему
    queue = await get_queue(clan_id)
    if queue:
        next_player = queue[0]
        # Добавляем 1 попытку следующему игроку (передача хода)
        await add_to_queue(clan_id, next_player["user_id"], attempts=1)
        # Уведомляем в группу
        # (опционально, можно убрать если спамит)
        # duel_chat = duel.get("chat_id")
        # if duel_chat:
        #     pass  # уведомление о передаче хода


@router.message(Command("reset"))
async def cmd_reset(message: Message):
    """Сбрасывает зависшие игры (для теста)."""
    user_id = message.from_user.id
    session = await get_active_session_for_user(user_id)
    if session:
        await update_session(session["id"], status="lost")
        await message.answer("❌ Зависшая игра сброшена.")
    else:
        await message.answer("Нет активных игр.")
