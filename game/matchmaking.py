"""
Система подбора кланов для дуэли.

Логика:
- Кланы которые ещё не играли в этом цикле идут в приоритете
- Из них выбирается пара: аутсайдер (меньше Al) vs лидер (больше Al)
- После боя аутсайдеров следующий бой: лидер vs следующий по очереди
- Участники ротируются внутри клана — каждый должен сыграть прежде чем кто-то сыграет второй раз
"""
import random
from db.clan_queries import get_all_clans, get_clan_members
from db.duel_queries import get_queue, add_to_queue, get_next_player


async def get_next_duel_pair(war_id: int) -> tuple[dict, dict, int, int] | None:
    """
    Возвращает (clan1, clan2, player1_id, player2_id) или None.
    """
    clans = await get_all_clans(war_id)
    if len(clans) < 2:
        return None

    # Выбираем два клана по балансу: аутсайдер vs лидер
    sorted_clans = sorted(clans, key=lambda c: c["al"])
    clan_loser = sorted_clans[0]
    clan_leader = sorted_clans[-1]

    if clan_loser["id"] == clan_leader["id"]:
        # Только 2 клана — просто берём их
        clan1, clan2 = sorted_clans[0], sorted_clans[1]
    else:
        clan1, clan2 = clan_loser, clan_leader

    # Выбираем игроков из очереди каждого клана
    p1 = await _pick_player(clan1["id"])
    p2 = await _pick_player(clan2["id"])

    if p1 is None or p2 is None:
        return None

    return clan1, clan2, p1, p2


async def _pick_player(clan_id: int) -> int | None:
    """Выбирает следующего игрока из очереди клана. Если очередь пуста — перезаполняет."""
    queue = await get_queue(clan_id)
    if not queue:
        await _refill_queue(clan_id)
        queue = await get_queue(clan_id)
    if not queue:
        return None
    return queue[0]["user_id"]


async def _refill_queue(clan_id: int):
    """Добавляет всех участников клана в очередь по 1 попытке."""
    members = await get_clan_members(clan_id)
    for m in members:
        await add_to_queue(clan_id, m["user_id"], attempts=1)
