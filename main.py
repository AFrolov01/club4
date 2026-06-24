from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from db.clan_queries import (
    create_clan, get_all_clans, get_clan_by_id, get_user_clan,
    get_clan_members, join_clan, leave_clan, kick_member,
    transfer_leadership, get_active_war, delete_clan
)

router = Router()

class CreateClanFSM(StatesGroup):
    waiting_name = State()
    waiting_avatar = State()
    waiting_deviz = State()

# ===== СОЗДАНИЕ КЛАНА =====

@router.message(Command("createclan"))
async def cmd_create_clan(message: Message, state: FSMContext):
    existing = await get_user_clan(message.from_user.id)
    if existing:
        await message.answer(f"⚠️ Ты уже состоишь в клане <b>{existing['name']}</b>.\nСначала выйди: /leaveclan", parse_mode="HTML")
        return
    await state.set_state(CreateClanFSM.waiting_name)
    await message.answer("⚔️ <b>Создание клана</b>\n\nВведи название клана:", parse_mode="HTML")

@router.message(CreateClanFSM.waiting_name)
async def fsm_clan_name(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("❌ Создание клана отменено. Напиши /createclan чтобы начать заново.")
        return
    name = message.text.strip()
    if len(name) < 2 or len(name) > 32:
        await message.answer("❌ Название должно быть от 2 до 32 символов. Попробуй ещё раз:")
        return
    await state.update_data(name=name)
    await state.set_state(CreateClanFSM.waiting_avatar)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Пропустить →", callback_data="clan_skip_avatar")
    ]])
    await message.answer(
        "🖼 Отправь аватарку клана (фото) или нажми <b>Пропустить</b>:",
        parse_mode="HTML", reply_markup=kb
    )

@router.message(CreateClanFSM.waiting_avatar, F.photo)
async def fsm_clan_avatar_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(avatar=file_id)
    await state.set_state(CreateClanFSM.waiting_deviz)
    await message.answer("✍️ Введи девиз клана (или напиши <b>-</b> чтобы пропустить):", parse_mode="HTML")

@router.callback_query(F.data == "clan_skip_avatar", CreateClanFSM.waiting_avatar)
async def fsm_clan_skip_avatar(call: CallbackQuery, state: FSMContext):
    await state.update_data(avatar=None)
    await state.set_state(CreateClanFSM.waiting_deviz)
    await call.message.edit_text("✍️ Введи девиз клана (или напиши <b>-</b> чтобы пропустить):", parse_mode="HTML")

@router.message(CreateClanFSM.waiting_deviz)
async def fsm_clan_deviz(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("❌ Создание клана отменено. Напиши /createclan чтобы начать заново.")
        return
    deviz = message.text.strip()
    if deviz == "-":
        deviz = ""
    data = await state.get_data()
    await state.clear()
    war = await get_active_war()
    war_id = war["id"] if war else 1
    clan_id = await create_clan(
        name=data["name"],
        deviz=deviz,
        avatar_file_id=data.get("avatar"),
        creator_id=message.from_user.id,
        war_id=war_id
    )
    if clan_id is None:
        await message.answer("❌ Клан с таким названием уже существует. Попробуй другое имя.")
        return
    await join_clan(message.from_user.id, clan_id, message.from_user.username or "", message.from_user.full_name)
    await message.answer(
        f"✅ Клан <b>{data['name']}</b> создан!\n"
        f"{'📜 Девиз: ' + deviz if deviz else ''}\n\n"
        f"Другие могут вступить через /join",
        parse_mode="HTML"
    )

# ===== ВСТУПЛЕНИЕ В КЛАН =====

@router.message(Command("join"))
async def cmd_join(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.clear()
    existing = await get_user_clan(message.from_user.id)
    if existing:
        await message.answer(f"⚠️ Ты уже в клане <b>{existing['name']}</b>.", parse_mode="HTML")
        return
    war = await get_active_war()
    war_id = war["id"] if war else 1
    clans = await get_all_clans(war_id)
    if not clans:
        await message.answer("😔 Пока нет ни одного клана. Создай первый: /createclan")
        return
    await state.update_data(join_index=0, join_clans=[c["id"] for c in clans])
    await _show_clan_card(message, clans[0], 0, len(clans), edit=False)


async def _show_clan_card(target, clan: dict, idx: int, total: int, edit: bool = False):
    """
    target — либо Message (при первом вызове), либо Message из CallbackQuery (при навигации).
    edit=True — редактировать существующее сообщение вместо отправки нового.
    """
    members = await get_clan_members(clan["id"])
    text = (
        f"⚔️ <b>{clan['name']}</b>\n"
        f"{'📜 ' + clan['deviz'] if clan['deviz'] else ''}\n\n"
        f"👥 Участников: {len(members)}\n"
        f"💠 Al: {clan['al']}\n\n"
        f"{idx+1} / {total}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️", callback_data=f"join_nav_{idx-1}"),
        InlineKeyboardButton(text="✅ Выбрать", callback_data=f"join_select_{clan['id']}"),
        InlineKeyboardButton(text="➡️", callback_data=f"join_nav_{idx+1}"),
    ]])

    if clan.get("avatar_file_id"):
        if edit:
            # Редактируем медиа — не создаём новое сообщение
            try:
                await target.edit_media(
                    InputMediaPhoto(media=clan["avatar_file_id"], caption=text, parse_mode="HTML"),
                    reply_markup=kb
                )
            except Exception:
                pass  # Если не удалось — просто оставляем как есть
        else:
            await target.answer_photo(clan["avatar_file_id"], caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        if edit:
            try:
                await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
        else:
            await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("join_nav_"))
async def join_nav(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split("_")[2])
    data = await state.get_data()
    clan_ids = data.get("join_clans", [])
    if not clan_ids:
        await call.answer("Сессия устарела. Напиши /join снова.")
        return

    idx = max(0, min(idx, len(clan_ids) - 1))
    await state.update_data(join_index=idx)
    clan = await get_clan_by_id(clan_ids[idx])
    if clan:
        # edit=True — обновляем то же самое сообщение, без спама
        await _show_clan_card(call.message, clan, idx, len(clan_ids), edit=True)
    await call.answer()

@router.callback_query(F.data.startswith("join_select_"))
async def join_select(call: CallbackQuery, state: FSMContext):
    clan_id = int(call.data.split("_")[2])
    await state.clear()
    existing = await get_user_clan(call.from_user.id)
    if existing:
        await call.answer("Ты уже в клане!", show_alert=True)
        return
    clan = await get_clan_by_id(clan_id)
    if not clan:
        await call.answer("Клан не найден.", show_alert=True)
        return
    ok = await join_clan(call.from_user.id, clan_id, call.from_user.username or "", call.from_user.full_name)
    if ok:
        await call.message.edit_text(
            f"✅ Ты вступил в клан <b>{clan['name']}</b>!\nНапиши /clan чтобы посмотреть профиль клана.",
            parse_mode="HTML"
        )
    else:
        await call.answer("Не удалось вступить.", show_alert=True)

# ===== ПРОФИЛЬ КЛАНА =====

@router.message(Command("clan"))
async def cmd_clan(message: Message):
    clan = await get_user_clan(message.from_user.id)
    if not clan:
        await message.answer("😔 Ты не состоишь ни в одном клане.\nВступи через /join или создай /createclan")
        return
    members = await get_clan_members(clan["id"])
    member_lines = []
    for m in members:
        name = f"@{m['username']}" if m["username"] else m["full_name"]
        crown = " 👑" if m["user_id"] == clan["creator_id"] else ""
        member_lines.append(f" • {name}{crown}")
    best_mult_line = ""
    if clan["best_multiplier"] > 1.0 and clan["best_multiplier_username"]:
        best_mult_line = f"🎰 Лучший множитель: x{clan['best_multiplier']:.2f} (@{clan['best_multiplier_username']})\n"
    text = (
        f"⚔️ <b>{clan['name']}</b>\n"
        f"{'📜 ' + clan['deviz'] if clan['deviz'] else ''}\n\n"
        f"💠 <b>Al:</b> {clan['al']}\n"
        f"🏆 Побед: {clan['wins']} | 💀 Поражений: {clan['losses']}\n"
        f"🔥 Текущая серия: {clan['current_win_streak']}\n"
        f"📈 Макс. серия: {clan['max_win_streak']}\n"
        f"{best_mult_line}"
        f"\n👥 <b>Участники ({len(members)}):</b>\n"
        + "\n".join(member_lines)
    )
    if clan.get("avatar_file_id"):
        await message.answer_photo(clan["avatar_file_id"], caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")

# ===== ВЫХОД ИЗ КЛАНА =====

@router.message(Command("leaveclan"))
async def cmd_leave(message: Message):
    clan = await get_user_clan(message.from_user.id)
    if not clan:
        await message.answer("Ты не состоишь ни в каком клане.")
        return
    if clan["creator_id"] == message.from_user.id:
        members = await get_clan_members(clan["id"])
        if len(members) > 1:
            await message.answer("⚠️ Ты создатель клана. Сначала передай лидерство через /transferlead @юзер")
            return
    await leave_clan(message.from_user.id)
    await message.answer(f"Ты вышел из клана <b>{clan['name']}</b>.", parse_mode="HTML")

# ===== УДАЛЕНИЕ КЛАНА =====

@router.message(Command("deleteclan"))
async def cmd_delete_clan(message: Message):
    clan = await get_user_clan(message.from_user.id)
    if not clan:
        await message.answer("Ты не состоишь ни в каком клане.")
        return
    if clan["creator_id"] != message.from_user.id:
        await message.answer("⛔ Только лидер клана может его удалить.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"confirm_delete_{clan['id']}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
    ]])
    await message.answer(
        f"⚠️ Ты уверен что хочешь удалить клан <b>{clan['name']}</b>?\n"
        f"Все участники будут исключены. Это действие необратимо.",
        parse_mode="HTML", reply_markup=kb
    )

@router.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_clan(call: CallbackQuery):
    clan_id = int(call.data.split("_")[2])
    clan = await get_clan_by_id(clan_id)
    if not clan or clan["creator_id"] != call.from_user.id:
        await call.answer("⛔ Нет прав.", show_alert=True)
        return
    ok = await delete_clan(clan_id, call.from_user.id)
    if ok:
        await call.message.edit_text(f"🗑 Клан <b>{clan['name']}</b> удалён.", parse_mode="HTML")
    else:
        await call.answer("❌ Не удалось удалить клан.", show_alert=True)

@router.callback_query(F.data == "cancel_delete")
async def cancel_delete_clan(call: CallbackQuery):
    await call.message.edit_text("✅ Удаление отменено.")

# ===== КИК =====

@router.message(Command("kick"))
async def cmd_kick(message: Message):
    clan = await get_user_clan(message.from_user.id)
    if not clan or clan["creator_id"] != message.from_user.id:
        await message.answer("⛔ Только лидер клана может кикать участников.")
        return
    if not message.reply_to_message:
        await message.answer("Ответь на сообщение участника которого хочешь кикнуть.")
        return
    target = message.reply_to_message.from_user
    ok = await kick_member(clan["id"], target.id, message.from_user.id)
    if ok:
        await message.answer(f"✅ {target.full_name} исключён из клана.")
    else:
        await message.answer("❌ Не удалось кикнуть участника.")

# ===== ПЕРЕДАЧА ЛИДЕРСТВА =====

@router.message(Command("transferlead"))
async def cmd_transfer(message: Message):
    clan = await get_user_clan(message.from_user.id)
    if not clan or clan["creator_id"] != message.from_user.id:
        await message.answer("⛔ Только лидер может передавать лидерство.")
        return
    if not message.reply_to_message:
        await message.answer("Ответь на сообщение участника которому хочешь передать лидерство.")
        return
    target = message.reply_to_message.from_user
    ok = await transfer_leadership(clan["id"], target.id, message.from_user.id)
    if ok:
        await message.answer(f"👑 Лидерство передано {target.full_name}!")
    else:
        await message.answer("❌ Этот участник не состоит в твоём клане.")

# ===== ТОП КЛАНОВ =====

@router.message(Command("top"))
async def cmd_top(message: Message):
    war = await get_active_war()
    if not war:
        await message.answer("Война кланов ещё не началась.")
        return
    clans = await get_all_clans(war["id"])
    if not clans:
        await message.answer("Пока нет ни одного клана.")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = ["💠 <b>Война кланов — таблица Al:</b>\n"]
    for i, c in enumerate(clans):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} <b>{c['name']}</b> — {c['al']} Al")
    started = war["started_at"][:10]
    lines.append(f"\n📅 Война началась: {started}")
    await message.answer("\n".join(lines), parse_mode="HTML")
