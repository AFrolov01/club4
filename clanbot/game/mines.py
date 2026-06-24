import random
import json
from config import MULTIPLIERS, FIELD_SIZE, MAX_MINES, LOSE_MULTIPLIER, MIN_AL


def generate_field(mines: int) -> list[int]:
    """Генерирует поле 5x5. 1 = мина, 0 = пусто."""
    total = FIELD_SIZE * FIELD_SIZE
    field = [0] * total
    mine_positions = random.sample(range(total), mines)
    for pos in mine_positions:
        field[pos] = 1
    return field


def get_multipliers(mines: int) -> list[float]:
    return MULTIPLIERS.get(mines, MULTIPLIERS[1])


def get_current_multiplier(mines: int, step: int) -> float:
    mults = get_multipliers(mines)
    if step == 0:
        return 1.0
    idx = step - 1
    if idx >= len(mults):
        return mults[-1]
    return mults[idx]


def get_next_multipliers_str(mines: int, step: int, count: int = 5) -> str:
    """Возвращает строку с прогрессией следующих множителей."""
    mults = get_multipliers(mines)
    start = step  # следующий шаг
    shown = mults[start:start + count]
    if not shown:
        return "максимум достигнут"
    parts = [f"x{m:.2f}" for m in shown]
    if start + count < len(mults):
        parts.append("...")
    return " ➡️ ".join(parts)


def get_full_progression_str(mines: int) -> str:
    """Полная прогрессия для отображения при выборе мин."""
    mults = get_multipliers(mines)
    shown = mults[:6]
    parts = [f"x{m:.2f}" for m in shown]
    if len(mults) > 6:
        parts.append("...")
    return " ➡️ ".join(parts)


def open_cell(field: list[int], opened: list[int], pos: int) -> bool:
    """Открывает клетку. Возвращает True если мина."""
    opened.append(pos)
    return field[pos] == 1


def calc_new_al(current_al: int, multiplier: float, won: bool) -> int:
    if won:
        new_al = int(current_al * multiplier)
    else:
        new_al = int(current_al * LOSE_MULTIPLIER)
    return max(new_al, MIN_AL)


def build_field_buttons(field: list[int], opened: list[int], game_over: bool = False):
    """Строит inline keyboard для поля 5x5."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for row in range(FIELD_SIZE):
        row_btns = []
        for col in range(FIELD_SIZE):
            pos = row * FIELD_SIZE + col
            if pos in opened:
                if field[pos] == 1:
                    text = "💣"
                else:
                    text = "💎"
                btn = InlineKeyboardButton(text=text, callback_data=f"cell_noop_{pos}")
            else:
                if game_over and field[pos] == 1:
                    text = "💣"
                    btn = InlineKeyboardButton(text=text, callback_data=f"cell_noop_{pos}")
                else:
                    text = "❓"
                    btn = InlineKeyboardButton(text=text, callback_data=f"cell_{pos}")
            row_btns.append(btn)
        buttons.append(row_btns)
    # Кнопка забрать
    if not game_over:
        buttons.append([InlineKeyboardButton(text="✅ Забрать очки", callback_data="cell_cashout")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def mines_choice_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [[
        InlineKeyboardButton(text=f"{i}️⃣", callback_data=f"mines_{i}")
        for i in range(1, 7)
    ]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
