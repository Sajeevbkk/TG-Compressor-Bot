import logging
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

import config
from handlers.queue_manager import queue_manager

logger = logging.getLogger(__name__)


async def is_owner_cb(_, __, query: CallbackQuery) -> bool:
    """Strict owner check for callback queries."""
    return bool(query.from_user and query.from_user.id == config.OWNER_ID)


owner_cb_filter = filters.create(is_owner_cb)


def register_callback_handlers(app: Client) -> None:
    """Register callback query handlers."""

    @app.on_callback_query(owner_cb_filter & filters.regex(r"^cmp:(?P<task_id>[a-f0-9]+):(?P<action>.+)$"))
    async def compression_callback(client: Client, query: CallbackQuery):
        match = query.matches[0]
        task_id = match.group("task_id")
        action = match.group("action")

        await query.answer()

        choice: Optional[int] = None
        if action == "cancel":
            choice = -1
        elif action == "same":
            choice = None
        elif action.isdigit():
            choice = int(action)
        else:
            await query.answer("⚠️ Unknown option selected.", show_alert=True)
            return

        handled = queue_manager.handle_callback_choice(task_id, choice)
        if not handled:
            await query.answer("⚠️ This task has already been processed or expired.", show_alert=True)
