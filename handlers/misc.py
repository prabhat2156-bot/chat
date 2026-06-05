import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command, CommandStart

from database.mongodb import get_db
from config import GAME_NAMES

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>PvP Gaming Arena Bot</b>\n\n"
        "<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> The ultimate battle referee for your group!\n\n"
        "Just add me to any group and start playing.\n"
        "Use /help to see all commands.",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>PvP Gaming Arena Bot — Commands</b>\n\n"

        "<b><tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> Play:</b>\n"
        "• /challenge @user — Quick free match (no payment)\n"
        "• /battle @user — <b>Paid battle</b> with real stakes + admin approval\n\n"

        "<b><tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> Stats:</b>\n"
        "• /profile — View any player's win/loss/draw stats\n"
        "• /mystats — Your own stats (works in DM too)\n"
        "• /mybattles — Your paid battle history + earnings\n"
        "• /leaderboard — Top 10 players in the group\n\n"

        "<b><tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> Tournament:</b>\n"
        "• /tournament — Start a bracket tournament (group admins)\n\n"

        "<b><tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> My Game:</b>\n"
        "• /mygame — See your active game(s) with ID in this group\n\n"

        "<b><tg-emoji emoji-id='6271674836628541366'>🛑</tg-emoji> Cancel Your Game:</b>\n"
        "• /cancel — See your active game with its ID\n"
        "• /cancel A1B2C3D4 — Cancel your own match or battle by ID\n\n"

        "<b><tg-emoji emoji-id='5341715473882955310'>⚙️</tg-emoji> Admin Commands:</b>\n"
        "• /feeset 10 — Set battle fee % for this group (admins only)\n"
        "• /fee — Show current battle fee\n"
        "• /history — See all active matches & battles in the group\n"
        "• /endall — Cancel ALL active games in the group\n"
        "• /cancel A1B2C3D4 — Admins can cancel any game by ID\n"
        "• /cancelmatch A1B2C3D4 — Cancel a specific match by ID\n"
        "• /cancelbattle A1B2C3D4 — Cancel a specific battle by ID\n\n"

        "<b><tg-emoji emoji-id='4958725487682650920'>👑</tg-emoji> Owner Commands (DM only):</b>\n"
        "• /reset — Wipe ALL bot data (irreversible!)\n"
        "• /lookup A1B2C3D4 — Full details of any past match or battle\n"
        "• /allhistory — Last 20 completed matches & battles (all groups)\n\n"

        "<b><tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Games (10 total):</b>\n"
        "<tg-emoji emoji-id='5897476360720356729'>🎲</tg-emoji> Dice  <tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> Dart  <tg-emoji emoji-id='6034910005612778344'>🏀</tg-emoji> Basketball  <tg-emoji emoji-id='6334540251465254516'>⚽</tg-emoji> Football\n"
        "<tg-emoji emoji-id='5891120371762990493'>🎳</tg-emoji> Bowling  <tg-emoji emoji-id='5235989279024373566'>🎰</tg-emoji> Slots  <tg-emoji emoji-id='6325790754543241229'>🪨</tg-emoji> RPS  ⭕ Tic Tac Toe\n"
        "<tg-emoji emoji-id='6237485887635067877'>🔢</tg-emoji> Guess Number  <tg-emoji emoji-id='4956719506027185156'>💎</tg-emoji> Treasure Hunt\n\n"

        "<b><tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> /challenge vs /battle:</b>\n"
        "• <b>/challenge</b> — Free, both confirm → play immediately\n"
        "• <b>/battle</b> — Pick game + rounds + amount → both confirm\n"
        "  → both pay admin → admin approves → play → winner gets pot\n\n"

        "<b><tg-emoji emoji-id='5197269100878907942'>📋</tg-emoji> Rules:</b>\n"
        "• Multiple matches can run at once in each group\n"
        "• 60s per turn — timeout = forfeit\n"
        "• <tg-emoji emoji-id='4956337889593000947'>🚫</tg-emoji> Forfeit button in every game"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("games"))
async def cmd_games(message: Message):
    text = (
        "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Available Games (10)</b>\n\n"

        "<b><tg-emoji emoji-id='5897476360720356729'>🎲</tg-emoji> Telegram Dice Games:</b>\n"
        "<tg-emoji emoji-id='5897476360720356729'>🎲</tg-emoji> <b>Dice Roll</b> — Roll highest number\n"
        "<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>Dart</b> — Throw highest score\n"
        "<tg-emoji emoji-id='6034910005612778344'>🏀</tg-emoji> <b>Basketball</b> — Score most points\n"
        "<tg-emoji emoji-id='6334540251465254516'>⚽</tg-emoji> <b>Football</b> — Kick it in\n"
        "<tg-emoji emoji-id='5891120371762990493'>🎳</tg-emoji> <b>Bowling</b> — Strike!\n"
        "<tg-emoji emoji-id='5235989279024373566'>🎰</tg-emoji> <b>Slot Machine</b> — Spin to win\n\n"

        "<b><tg-emoji emoji-id='6301042242450625545'>🕹</tg-emoji>️ Strategy Games:</b>\n"
        "<tg-emoji emoji-id='6325790754543241229'>🪨</tg-emoji> <b>Rock Paper Scissors</b> — Classic, simultaneous reveal\n"
        "⭕ <b>Tic Tac Toe</b> — 3×3 board, X vs O\n"
        "<tg-emoji emoji-id='6237485887635067877'>🔢</tg-emoji> <b>Guess the Number</b> — 1–100, alternate guesses\n"
        "<tg-emoji emoji-id='4956719506027185156'>💎</tg-emoji> <b>Treasure Hunt</b> — Flip cells, avoid <tg-emoji emoji-id='5280569974404966639'>💣</tg-emoji> bombs!\n\n"

        "Start with /challenge @player or /battle @player!"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("mygame"))
async def cmd_mygame(message: Message):
    """Shows the user their active game(s) in this group with Game IDs."""
    if message.chat.type == "private":
        await message.answer(
            "Use <code>/mygame</code> inside a group to see your active games there.",
            parse_mode="HTML",
        )
        return

    uid      = message.from_user.id
    group_id = message.chat.id
    db       = get_db()

    my_match = await db.matches.find_one({
        "group_id": group_id,
        "status": "active",
        "$or": [{"player1_id": uid}, {"player2_id": uid}],
    })
    my_battle = await db.battles.find_one({
        "group_id": group_id,
        "status": {"$nin": ["completed", "cancelled", "declined"]},
        "$or": [{"challenger_id": uid}, {"opponent_id": uid}],
    })

    if not my_match and not my_battle:
        await message.answer(
            "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>You have no active games in this group.</b>\n\n"
            "Start one:\n"
            "• /challenge @player — free match\n"
            "• /battle @player — paid battle",
            parse_mode="HTML",
        )
        return

    lines = [f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Your Active Games — {message.chat.title}</b>\n"]

    if my_match:
        short    = my_match["match_id"][:8].upper()
        gname    = GAME_NAMES.get(my_match["game"], my_match["game"])
        opp      = my_match["player2_name"] if uid == my_match["player1_id"] else my_match["player1_name"]
        is_your_turn = my_match.get("current_turn") == uid
        turn_tag = "  ⬅️ <b>YOUR TURN</b>" if is_your_turn else ""
        battle_tag = "\n  _(inside a /battle round)_" if my_match.get("battle_id") else ""
        lines.append(
            f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Match</b>{battle_tag}\n"
            f"  🆔 <code>{short}</code>\n"
            f"  <tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> {gname}{turn_tag}\n"
            f"  🆚 vs @{opp}\n"
            f"  <tg-emoji emoji-id='4956282853882069908'>➡️</tg-emoji> Cancel: <code>/cancel {short}</code>"
        )

    if my_battle:
        short    = my_battle["battle_id"][:8].upper()
        gname    = GAME_NAMES.get(my_battle.get("game") or "", "—") if my_battle.get("game") else "—"
        opp      = my_battle["opponent_name"] if uid == my_battle["challenger_id"] else my_battle["challenger_name"]
        role     = "Challenger" if uid == my_battle["challenger_id"] else "Opponent"
        amount   = f"₹{my_battle['amount']}" if my_battle.get("amount") else "amount TBD"
        smap = {
            "form_filling":           "<tg-emoji emoji-id='6141066526129653847'>📝</tg-emoji> Filling form",
            "pending_confirmation":   "⏳ Waiting for confirmation",
            "pending_payment":        "<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> Waiting for payment",
            "pending_ready":          "<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> Waiting for ready",
            "active":                 "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Rounds in progress",
            "pending_payout":         "<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Waiting for payout",
            "draw_pending":           "<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> Draw — choose split/rematch",
            "draw_rematch_pending":   "<tg-emoji emoji-id='4956371914323920049'>🔄</tg-emoji> Rematch confirmation pending",
        }
        slabel = smap.get(my_battle["status"], my_battle["status"])
        score  = ""
        if my_battle.get("total_rounds"):
            p1w   = my_battle.get("p1_wins", 0)
            p2w   = my_battle.get("p2_wins", 0)
            draws = my_battle.get("round_draws", 0)
            dr    = f"  ({draws} draw{'s' if draws != 1 else ''})" if draws else ""
            score = f"\n  <tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> Score: {p1w}–{p2w}{dr}  (Round {my_battle.get('current_round',0)}/{my_battle['total_rounds']})"

        lines.append(
            f"\n<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <b>Paid Battle</b>  [{role}]\n"
            f"  🆔 <code>{short}</code>\n"
            f"  <tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> {gname}  ·  {amount}\n"
            f"  🆚 vs @{opp}\n"
            f"  <tg-emoji emoji-id='4956232383721374836'>📌</tg-emoji> {slabel}{score}\n"
            f"  <tg-emoji emoji-id='4956282853882069908'>➡️</tg-emoji> Cancel: <code>/cancel {short}</code>"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")
