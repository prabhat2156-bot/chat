import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from database.mongodb import get_db
from database.models import now_utc
from config import OWNER_ID, DEFAULT_FEE_PERCENT

logger = logging.getLogger(__name__)
router = Router()


def _is_owner(user_id: int) -> bool:
    return OWNER_ID != 0 and user_id == OWNER_ID


@router.message(Command("addgroup"))
async def cmd_addgroup(message: Message):
    if not _is_owner(message.from_user.id):
        return  # silently ignore

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer(
            "⚙️ <b>Add Group</b>\n\nUsage: <code>/addgroup &lt;group_id&gt;</code>\n\n"
            "To get a group ID, forward any group message to @userinfobot or add the bot to the group and it will report the ID.",
            parse_mode="HTML",
        )
        return

    try:
        group_id = int(args[1])
    except ValueError:
        await message.answer("❌ Invalid group ID. Must be a number (e.g. -1001234567890).")
        return

    db = get_db()
    existing = await db.group_settings.find_one({"group_id": group_id})
    if existing and existing.get("allowed"):
        await message.answer(f"✅ Group <code>{group_id}</code> is already allowed.", parse_mode="HTML")
        return

    await db.group_settings.update_one(
        {"group_id": group_id},
        {
            "$set": {
                "group_id": group_id,
                "allowed": True,
                "fee_percent": DEFAULT_FEE_PERCENT,
                "added_by": message.from_user.id,
                "added_at": now_utc(),
                "updated_at": now_utc(),
            }
        },
        upsert=True,
    )
    await message.answer(
        f"✅ <b>Group Added!</b>\n\n"
        f"🆔 Group ID: <code>{group_id}</code>\n"
        f"💰 Default fee: <b>{DEFAULT_FEE_PERCENT}%</b>\n\n"
        f"Bot is now active in this group.",
        parse_mode="HTML",
    )


@router.message(Command("removegroup"))
async def cmd_removegroup(message: Message):
    if not _is_owner(message.from_user.id):
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer("Usage: <code>/removegroup &lt;group_id&gt;</code>", parse_mode="HTML")
        return

    try:
        group_id = int(args[1])
    except ValueError:
        await message.answer("❌ Invalid group ID.")
        return

    db = get_db()
    await db.group_settings.update_one(
        {"group_id": group_id},
        {"$set": {"allowed": False, "updated_at": now_utc()}},
    )
    await message.answer(f"✅ Group <code>{group_id}</code> has been disabled.", parse_mode="HTML")


@router.message(Command("setfee"))
async def cmd_setfee(message: Message):
    if not _is_owner(message.from_user.id):
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer(
            "Usage: <code>/setfee &lt;group_id&gt; &lt;percent&gt;</code>\n\n"
            "Example: <code>/setfee -1001234567890 10</code>  (10% fee)",
            parse_mode="HTML",
        )
        return

    try:
        group_id = int(args[1])
        percent = float(args[2])
        if not (0 <= percent <= 50):
            raise ValueError
    except ValueError:
        await message.answer("❌ Invalid values. Fee must be 0-50%.")
        return

    db = get_db()
    await db.group_settings.update_one(
        {"group_id": group_id},
        {"$set": {"fee_percent": percent, "updated_at": now_utc()}},
        upsert=True,
    )
    await message.answer(
        f"✅ <b>Fee Updated!</b>\n\n"
        f"🆔 Group: <code>{group_id}</code>\n"
        f"💰 New fee: <b>{percent}%</b>",
        parse_mode="HTML",
    )


@router.message(Command("listgroups"))
async def cmd_listgroups(message: Message):
    if not _is_owner(message.from_user.id):
        return

    db = get_db()
    groups = await db.group_settings.find({"allowed": True}).to_list(length=100)
    if not groups:
        await message.answer("📋 No groups are currently enabled.")
        return

    lines = ["📋 <b>Enabled Groups</b>\n"]
    for g in groups:
        gid = g["group_id"]
        fee = g.get("fee_percent", DEFAULT_FEE_PERCENT)
        lines.append(f"• <code>{gid}</code>  —  Fee: <b>{fee}%</b>")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("ownerhelp"))
async def cmd_ownerhelp(message: Message):
    if not _is_owner(message.from_user.id):
        return

    await message.answer(
        "⚙️ <b>Owner Commands (DM only)</b>\n\n"
        "<code>/addgroup &lt;group_id&gt;</code> — Enable bot in a group\n"
        "<code>/removegroup &lt;group_id&gt;</code> — Disable bot in a group\n"
        "<code>/setfee &lt;group_id&gt; &lt;percent&gt;</code> — Set battle fee % for a group\n"
        "<code>/listgroups</code> — List all enabled groups\n\n"
        "💡 Group IDs are negative numbers like <code>-1001234567890</code>",
        parse_mode="HTML",
    )
