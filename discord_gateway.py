import asyncio
import logging
import os

import discord
from dotenv import load_dotenv

import agent
from session import SessionManager

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"

logger = logging.getLogger(__name__)


def _is_allowed_user(user_id: int) -> bool:
    raw = os.getenv("DISCORD_ALLOWED_USER_IDS", "").strip()
    if not raw:
        return True
    allowed = {int(v.strip()) for v in raw.split(",") if v.strip()}
    return user_id in allowed


class DiscordYoloClient(discord.Client):
    def __init__(self, session_manager: SessionManager):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.session_manager = session_manager

    async def on_ready(self):
        logger.info("Discord gateway online as %s", self.user)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not _is_allowed_user(message.author.id):
            return

        text = (message.content or "").strip()
        if not text:
            return

        user_id = int(message.author.id)
        lock = self.session_manager.get_lock(user_id)
        async with lock:
            session = self.session_manager.get_or_create(user_id)
            if session.pending_confirmations:
                await message.reply(
                    "Pending confirmation exists. Resolve it in Telegram first."
                )
                return

            try:
                response = await agent.run_agent_turn(
                    text,
                    session,
                    signal_handler=None,
                    memory_service=self.session_manager.memory,
                )
            except agent.PendingConfirmationError as e:
                session.pending_confirmations.append(
                    {
                        "action": e.action,
                        "args": e.tool_args,
                        "tool_call_id": e.tool_call_id,
                    }
                )
                self.session_manager.save(user_id)
                await message.reply(
                    f"Confirmation required: `{e.action}` -> `{e.path}`. "
                    "Use Telegram callback controls or /cancel there."
                )
                return
            except Exception as ex:
                logger.exception("Discord turn failed")
                await message.reply(f"Error: {ex}")
                return

            self.session_manager.save(user_id)
            chunks = [
                response[i : i + 1900] for i in range(0, len(response), 1900)
            ] or ["(No response)"]
            for chunk in chunks:
                await message.reply(chunk)


async def run_discord_gateway() -> None:
    if not DISCORD_BOT_TOKEN:
        logger.warning("DISCORD_BOT_TOKEN not set; Discord gateway disabled.")
        return

    session_manager = SessionManager(
        timeout_minutes=int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
    )
    asyncio.create_task(session_manager.auto_expiry_task())
    client = DiscordYoloClient(session_manager)
    await client.start(DISCORD_BOT_TOKEN)
