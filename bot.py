import asyncio
import base64
import logging
import mimetypes
import os
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

import telegram.error
from colorama import Fore, Style, init
from dotenv import load_dotenv
from openai import AsyncOpenAI
from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup,
                      Update)
from telegram.constants import ParseMode
from telegram.ext import (Application, ApplicationBuilder,
                          CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)
from telegram.request import HTTPXRequest

import agent
from session import SessionManager

# Initialize colorama
init(autoreset=True)

# Load configuration
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS = [
    int(uid.strip())
    for uid in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
    if uid.strip()
]
VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"
TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))


def _get_int_env(name: str, default: int, min_value: int = 1) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < min_value:
        return default
    return value


MAX_TELEGRAM_UPLOAD_BYTES = _get_int_env("MAX_TELEGRAM_UPLOAD_BYTES", 25 * 1024 * 1024)
MAX_MEDIA_AI_BYTES = _get_int_env("MAX_MEDIA_AI_BYTES", 15 * 1024 * 1024)
ENABLE_MEDIA_AI_PIPELINE = os.getenv("ENABLE_MEDIA_AI_PIPELINE", "true").lower() == "true"
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", os.getenv("MODEL_NAME", "gpt-4o-mini"))
TRANSCRIPTION_MODEL_NAME = os.getenv("TRANSCRIPTION_MODEL_NAME", "gpt-4o-mini-transcribe")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

TELEGRAM_USE_WEBHOOK = os.getenv("TELEGRAM_USE_WEBHOOK", "false").lower() == "true"
TELEGRAM_WEBHOOK_LISTEN = os.getenv("TELEGRAM_WEBHOOK_LISTEN", "0.0.0.0")
TELEGRAM_WEBHOOK_PORT = _get_int_env("TELEGRAM_WEBHOOK_PORT", 8080)
TELEGRAM_WEBHOOK_PATH = os.getenv("TELEGRAM_WEBHOOK_PATH", "telegram").strip().strip("/")
TELEGRAM_WEBHOOK_URL_BASE = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip()
TELEGRAM_WEBHOOK_SECRET_TOKEN = os.getenv("TELEGRAM_WEBHOOK_SECRET_TOKEN", "").strip()

MEDIA_AI_CLIENT: Optional[AsyncOpenAI] = None
if ENABLE_MEDIA_AI_PIPELINE and OPENAI_API_KEY:
    MEDIA_AI_CLIENT = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        timeout=90.0,
    )

if not TOKEN:
    print(Fore.RED + "[ERROR] TELEGRAM_BOT_TOKEN is not set in .env.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Session Manager
session_manager = SessionManager(timeout_minutes=TIMEOUT_MINUTES)


def log_bot(user_id: int, tag: str, message: str, color: str = Fore.CYAN):
    if VERBOSE:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"{Fore.WHITE}[{user_id}] [{timestamp}] {color}{Style.BRIGHT}BOT-{tag}{Style.NORMAL} {message}"
        )


def escape_markdown(text: str) -> str:
    """Escape special MarkdownV2 characters for raw content."""
    escape_chars = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in escape_chars else c for c in text)


def build_telegram_signal_handler(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    async def telegram_signal_handler(signal_str: str) -> Optional[str]:
        if signal_str.startswith("__SEND_FILE__:"):
            file_path = signal_str.replace("__SEND_FILE__:", "")
            try:
                with open(file_path, "rb") as doc:
                    await context.bot.send_document(chat_id=chat_id, document=doc)
                return f"File `{os.path.basename(file_path)}` uploaded successfully."
            except Exception as e:
                return f"Failed to upload file: {e}"
        return None

    return telegram_signal_handler


def get_uploads_dir() -> Path:
    from tools.base import YOLO_ARTIFACTS

    uploads_dir = Path(YOLO_ARTIFACTS) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir


def build_webhook_url(base: str, path: str) -> str:
    if not path:
        return base.rstrip("/")
    cleaned_path = path.strip("/")
    if base.rstrip("/").endswith(f"/{cleaned_path}"):
        return base.rstrip("/")
    return f"{base.rstrip('/')}/{cleaned_path}"


def safe_upload_filename(file_name: Optional[str], fallback: str) -> str:
    base = Path(file_name).name if file_name else fallback
    cleaned = "".join(c for c in base if c.isalnum() or c in {"-", "_", "."})
    cleaned = cleaned.strip("._")
    return cleaned or fallback


def write_text_sidecar(file_path: Path, suffix: str, content: str) -> Optional[Path]:
    try:
        sidecar_path = file_path.with_name(file_path.name + suffix)
        sidecar_path.write_text(content, encoding="utf-8")
        return sidecar_path
    except Exception:
        logger.exception("Failed to write sidecar text")
        return None


def guess_file_extension(file_name: Optional[str], mime_type: Optional[str], default_ext: str) -> str:
    if file_name and Path(file_name).suffix:
        return Path(file_name).suffix
    if mime_type:
        guessed = mimetypes.guess_extension(mime_type)
        if guessed:
            return guessed
    return default_ext


async def maybe_extract_image_text(image_path: Path, mime_type: Optional[str]) -> Optional[str]:
    if MEDIA_AI_CLIENT is None:
        return None
    if not image_path.exists():
        return None
    if image_path.stat().st_size > MAX_MEDIA_AI_BYTES:
        return None

    effective_mime = mime_type or mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    try:
        image_bytes = image_path.read_bytes()
        b64 = base64.b64encode(image_bytes).decode("ascii")
        response = await MEDIA_AI_CLIENT.chat.completions.create(
            model=VISION_MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract as much visible text as possible (OCR) and then give a concise "
                                "description of the image. Keep the output plain text."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{effective_mime};base64,{b64}",
                            },
                        },
                    ],
                }
            ],
            temperature=0,
        )
        if not response.choices:
            return None
        text = response.choices[0].message.content or ""
        return text.strip() or None
    except Exception:
        logger.exception("Image OCR/extraction failed")
        return None


async def maybe_transcribe_audio(audio_path: Path) -> Optional[str]:
    if MEDIA_AI_CLIENT is None:
        return None
    if not audio_path.exists():
        return None
    if audio_path.stat().st_size > MAX_MEDIA_AI_BYTES:
        return None

    try:
        audio_bytes = audio_path.read_bytes()
        stream = BytesIO(audio_bytes)
        stream.name = audio_path.name
        transcription = await MEDIA_AI_CLIENT.audio.transcriptions.create(
            model=TRANSCRIPTION_MODEL_NAME,
            file=stream,
        )

        text = getattr(transcription, "text", None)
        if text is None:
            text = str(transcription)
        text = text.strip()
        return text or None
    except Exception:
        logger.exception("Audio transcription failed")
        return None


async def process_uploaded_artifact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    media_kind: str,
    local_path: Path,
    original_name: str,
    file_size: int,
    caption: str,
    extracted_text: Optional[str] = None,
    extracted_label: Optional[str] = None,
) -> None:
    relative_path = os.path.relpath(local_path, os.getcwd())
    user_id = update.effective_user.id
    log_bot(user_id, "UPLOAD", f"Saved `{relative_path}` ({file_size} bytes)", Fore.GREEN)

    extracted_path = None
    if extracted_text and extracted_label:
        sidecar_suffix = ".ocr.txt" if extracted_label == "OCR" else ".transcript.txt"
        extracted_path = write_text_sidecar(local_path, sidecar_suffix, extracted_text)

    if caption:
        prompt_parts = [
            f"The user uploaded a `{media_kind}` file at `{relative_path}`.",
            f"Original filename: `{original_name}`.",
            f"File size: `{file_size}` bytes.",
        ]
        if extracted_text and extracted_label:
            prompt_parts.append(f"Auto-generated {extracted_label} is available.")
            if extracted_path:
                prompt_parts.append(
                    f"{extracted_label} saved to: `{os.path.relpath(extracted_path, os.getcwd())}`."
                )
            prompt_parts.append(
                f"{extracted_label} preview:\n{extracted_text[:1200]}"
            )
        prompt_parts.append(f"User instruction: {caption}")
        await process_agent_turn(update, context, "\n\n".join(prompt_parts))
        return

    reply_lines = [
        "Upload saved successfully.",
        f"Type: {media_kind}",
        f"Path: {relative_path}",
    ]
    if extracted_text and extracted_label:
        if extracted_path:
            reply_lines.append(
                f"{extracted_label} file: {os.path.relpath(extracted_path, os.getcwd())}"
            )
        preview = extracted_text[:600]
        reply_lines.append(f"{extracted_label} preview: {preview}")
    reply_lines.append(
        "Send a follow-up instruction (example: summarize, extract action items, compare with another file)."
    )
    await update.message.reply_text("\n".join(reply_lines))


async def auth_check(update: Update) -> bool:
    """Check if the user is authorized. Silently ignore if not."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id not in ALLOWED_USER_IDS:
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    session_manager.clear(user_id)
    log_bot(user_id, "IN", "/start", Fore.CYAN)

    welcome = (
        "*Welcome to Yolo\\!*\n\n"
        "I am an autonomous system controller in Phase 3\\. "
        "Try commands like:\n"
        "• `Research the latest in AI and save an artifact`\n"
        "• `/mode yolo` then `Optimize my system_diagnosis skill`"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN_V2)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    log_bot(update.effective_user.id, "IN", "/help", Fore.CYAN)

    help_text = (
        "*Usage Guide*\n\n"
        "Simply send me instructions in plain English\\. Use `/mode yolo` for full autonomy\\.\n\n"
        "You can upload files directly in Telegram \\(optionally with a caption instruction\\) and I will save them to `artifacts/uploads`\\.\n\n"
        "Supported uploads: documents, photos \\(with OCR\\), audio/voice \\(with transcript when AI pipeline is enabled\\)\\.\n\n"
        "*Commands:*\n"
        "• `/experiences`: Technical lessons learned\n"
        "• `/schedules`: Recurring background tasks\n"
        "• `/memories`: Stored user context"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)


async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    if not update.message or not update.message.document:
        return

    user_id = update.effective_user.id
    document = update.message.document
    file_size = int(document.file_size or 0)

    if file_size > MAX_TELEGRAM_UPLOAD_BYTES:
        await update.message.reply_text(
            f"Upload rejected: file is too large ({file_size} bytes). "
            f"Limit is {MAX_TELEGRAM_UPLOAD_BYTES} bytes."
        )
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fallback_name = f"upload_{document.file_unique_id}.bin"
    filename = safe_upload_filename(document.file_name, fallback_name)
    local_path = get_uploads_dir() / f"{timestamp}_{filename}"

    try:
        tg_file = await context.bot.get_file(document.file_id)
        await tg_file.download_to_drive(custom_path=str(local_path))
    except Exception as e:
        logger.exception("Failed to download uploaded document")
        await update.message.reply_text(f"Failed to save uploaded file: {e}")
        return

    caption = (update.message.caption or "").strip()
    await process_uploaded_artifact(
        update,
        context,
        media_kind="document",
        local_path=local_path,
        original_name=document.file_name or filename,
        file_size=file_size,
        caption=caption,
    )


async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    if not update.message or not update.message.photo:
        return

    user_id = update.effective_user.id
    photo_sizes = update.message.photo
    photo = photo_sizes[-1]
    file_size = int(photo.file_size or 0)

    if file_size > MAX_TELEGRAM_UPLOAD_BYTES:
        await update.message.reply_text(
            f"Upload rejected: image is too large ({file_size} bytes). "
            f"Limit is {MAX_TELEGRAM_UPLOAD_BYTES} bytes."
        )
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    local_path = get_uploads_dir() / f"{timestamp}_photo_{photo.file_unique_id}.jpg"

    try:
        tg_file = await context.bot.get_file(photo.file_id)
        await tg_file.download_to_drive(custom_path=str(local_path))
    except Exception as e:
        logger.exception("Failed to download uploaded photo")
        await update.message.reply_text(f"Failed to save uploaded photo: {e}")
        return

    extracted_text = await maybe_extract_image_text(local_path, "image/jpeg")
    caption = (update.message.caption or "").strip()
    await process_uploaded_artifact(
        update,
        context,
        media_kind="photo",
        local_path=local_path,
        original_name=local_path.name,
        file_size=file_size,
        caption=caption,
        extracted_text=extracted_text,
        extracted_label="OCR",
    )
    log_bot(user_id, "UPLOAD", f"Saved photo `{local_path.name}` ({file_size} bytes)", Fore.GREEN)


async def handle_audio_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    if not update.message:
        return

    media = None
    media_kind = ""
    default_ext = ".bin"

    if update.message.voice:
        media = update.message.voice
        media_kind = "voice"
        default_ext = ".ogg"
    elif update.message.audio:
        media = update.message.audio
        media_kind = "audio"
        default_ext = ".mp3"

    if media is None:
        return

    file_size = int(getattr(media, "file_size", 0) or 0)
    if file_size > MAX_TELEGRAM_UPLOAD_BYTES:
        await update.message.reply_text(
            f"Upload rejected: {media_kind} is too large ({file_size} bytes). "
            f"Limit is {MAX_TELEGRAM_UPLOAD_BYTES} bytes."
        )
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_name = getattr(media, "file_name", None)
    mime_type = getattr(media, "mime_type", None)
    ext = guess_file_extension(file_name, mime_type, default_ext)
    safe_name = safe_upload_filename(file_name, f"{media_kind}_{media.file_unique_id}{ext}")
    local_path = get_uploads_dir() / f"{timestamp}_{safe_name}"

    try:
        tg_file = await context.bot.get_file(media.file_id)
        await tg_file.download_to_drive(custom_path=str(local_path))
    except Exception as e:
        logger.exception("Failed to download uploaded audio/voice")
        await update.message.reply_text(f"Failed to save uploaded {media_kind}: {e}")
        return

    transcript = await maybe_transcribe_audio(local_path)
    caption = (update.message.caption or "").strip()
    await process_uploaded_artifact(
        update,
        context,
        media_kind=media_kind,
        local_path=local_path,
        original_name=file_name or local_path.name,
        file_size=file_size,
        caption=caption,
        extracted_text=transcript,
        extracted_label="Transcript",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    log_bot(user_id, "IN", "/cancel", Fore.CYAN)

    if session.pending_confirmation:
        tool_name = session.pending_confirmation["action"]
        session.message_history.append(
            {
                "role": "tool",
                "tool_call_id": session.pending_confirmation["tool_call_id"],
                "name": tool_name,
                "content": "Action denied by user.",
            }
        )
        session.pending_confirmation = None
        session_manager.save(user_id)
        await update.message.reply_text("Pending action cancelled\\.")
    else:
        await update.message.reply_text("No pending action\\.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    log_bot(user_id, "IN", "/status", Fore.CYAN)

    history_len = len(session.message_history)
    has_pending = "Yes" if session.pending_confirmation else "No"
    current_mode = (
        "⚡ *YOLO* \\(Full Access\\)" if session.yolo_mode else "🛡️ *Safe* \\(HITL\\)"
    )
    think_state = "🧠 *ON*" if getattr(session, "think_mode", False) else "⚙️ *OFF*"
    think_policy = escape_markdown(getattr(session, "think_mode_policy", "auto"))
    sandbox_path = escape_markdown(os.getcwd())

    status_text = (
        f"*Status Report*\n"
        f"• Mode: {current_mode}\n"
        f"• Think mode: {think_state}\n"
        f"• Think policy: `{think_policy}`\n"
        f"• Messages in history: `{history_len}`\n"
        f"• Confirmation pending: *{has_pending}*\n"
        f"• Sandbox: `{sandbox_path}`"
    )
    await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN_V2)


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    args = context.args
    if not args:
        current = "Yolo" if session.yolo_mode else "Safe"
        await update.message.reply_text(
            f"Current mode: *{current}*\\. Use `/mode yolo` or `/mode safe`\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    choice = args[0].lower()
    if choice == "yolo":
        session.yolo_mode = True
        await update.message.reply_text(
            "⚡ *YOLO Mode Enabled*\\!", parse_mode=ParseMode.MARKDOWN_V2
        )
    elif choice == "safe":
        session.yolo_mode = False
        await update.message.reply_text(
            "🛡️ *Safe Mode Enabled*", parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            "Unknown mode\\. Use `/mode yolo` or `/mode safe`\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    session_manager.save(user_id)


async def think_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return

    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    args = context.args

    if not args:
        current = "On" if session.think_mode else "Off"
        policy = getattr(session, "think_mode_policy", "auto")
        await update.message.reply_text(
            f"Think mode: *{current}*\\. Policy: *{policy}*\\. Use `/think on`, `/think off`, or `/think auto`\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    choice = args[0].lower().strip()
    if choice in {"on", "true", "1", "enable", "enabled"}:
        session.think_mode_policy = "force_on"
        session.think_mode = True
        session_manager.save(user_id)
        await update.message.reply_text(
            "🧠 *Think Mode Enabled*\\. Policy set to *force_on*\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if choice in {"off", "false", "0", "disable", "disabled"}:
        session.think_mode_policy = "force_off"
        session.think_mode = False
        session_manager.save(user_id)
        await update.message.reply_text(
            "⚙️ *Think Mode Disabled*\\. Policy set to *force_off*\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if choice in {"auto", "smart", "default"}:
        session.think_mode_policy = "auto"
        session.think_mode = False
        session_manager.save(user_id)
        await update.message.reply_text(
            "🤖 *Think Mode Auto* enabled\\. I will turn think mode on for complex tasks automatically\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    await update.message.reply_text(
        "Unknown option\\. Use `/think on`, `/think off`, or `/think auto`\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    import tools

    tools_list = "*Available Tools:*\n\n"
    for tool_schema in tools.TOOLS_SCHEMAS:
        name = escape_markdown(tool_schema["function"]["name"])
        desc = escape_markdown(tool_schema["function"]["description"])
        tools_list += f"• `{name}`: {desc}\n"
    await send_long_message(update.effective_chat.id, tools_list, context)


async def experiences_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all technical lessons learned."""
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    log_bot(user_id, "IN", "/experiences", Fore.CYAN)

    try:
        from tools.experience_ops import list_experiences
        result = list_experiences(user_id)
        await send_long_message(update.effective_chat.id, result, context)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def schedules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List active scheduled tasks."""
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    log_bot(user_id, "IN", "/schedules", Fore.CYAN)

    try:
        from tools.cron_ops import get_scheduled_tasks
        result = get_scheduled_tasks(user_id)
        await send_long_message(update.effective_chat.id, result, context)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    log_bot(user_id, "IN", "/memories", Fore.CYAN)

    try:
        from tools.memory_ops import memory_list
        result = memory_list(user_id)
        await send_long_message(update.effective_chat.id, result, context)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def facts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    log_bot(user_id, "IN", "/facts", Fore.CYAN)

    try:
        # Ensure facts are refreshed before display.
        await agent.run_agent_turn(
            None,
            session,
            signal_handler=None,
            memory_service=session_manager.memory,
        )
        session_manager.save(user_id)

        if not session.message_history or session.message_history[0].get("role") != "system":
            await update.message.reply_text("No system prompt found for this session.")
            return

        content = str(session.message_history[0].get("content") or "")
        facts = agent.extract_auto_basic_facts(content)
        if not facts:
            await update.message.reply_text("No auto basic facts are currently injected.")
            return

        lines = [f"{i+1}. {fact}" for i, fact in enumerate(facts)]
        await send_long_message(
            update.effective_chat.id,
            "### Auto Basic Facts\n\n" + "\n".join(lines),
            context,
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    log_bot(user_id, "IN", "/forget", Fore.CYAN)

    try:
        from tools.memory_ops import memory_wipe
        result = memory_wipe(user_id)
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def get_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update) or not context.args:
        return
    path = context.args[0]
    try:
        from tools.base import resolve_and_verify_path
        resolved = resolve_and_verify_path(path, confirm_func=lambda a, t: True)
        if resolved.is_file():
            with open(resolved, "rb") as doc:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=doc)
        else:
            await update.message.reply_text("Error: path is not a file.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def process_agent_turn(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: Optional[str]
):
    user_id = update.effective_user.id
    
    async with session_manager.get_lock(user_id):
        session = session_manager.get_or_create(user_id)
        chat_id = update.effective_chat.id
        telegram_signal_handler = build_telegram_signal_handler(context, chat_id)

        try:
            response = await agent.run_agent_turn(
                user_text,
                session,
                signal_handler=telegram_signal_handler,
                memory_service=session_manager.memory,
            )
            await send_long_message(chat_id, response, context)
            session_manager.save(user_id)
        except agent.PendingConfirmationError as e:
            keyboard = [[InlineKeyboardButton("✅ Yes", callback_data="confirm"),
                         InlineKeyboardButton("❌ No", callback_data="deny")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            text = (
                f"⚠️ *Confirmation Required*\n"
                f"Action: `{escape_markdown(e.action)}`\n"
                f"Target: `{escape_markdown(e.path)}`"
            )
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
            session_manager.save(user_id)
        except Exception:
            logger.exception("Error in process_agent_turn")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    user_id = update.effective_user.id
    # Check pending confirmation outside the lock to prevent hanging if they just spam messages
    session = session_manager.get_or_create(user_id)
    if session.pending_confirmation:
        await update.message.reply_text("Pending confirmation required\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    await process_agent_turn(update, context, update.message.text)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    async with session_manager.get_lock(user_id):
        session = session_manager.get_or_create(user_id)
        if not session.pending_confirmation:
            return
        telegram_signal_handler = build_telegram_signal_handler(context, update.effective_chat.id)

        async def send_confirmation_prompt(err: agent.PendingConfirmationError):
            keyboard = [[InlineKeyboardButton("✅ Yes", callback_data="confirm"),
                         InlineKeyboardButton("❌ No", callback_data="deny")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            text = (
                f"⚠️ *Confirmation Required*\n"
                f"Action: `{escape_markdown(err.action)}`\n"
                f"Target: `{escape_markdown(err.path)}`"
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2,
            )

        pending = session.pending_confirmation
        session.pending_confirmation = None
        if query.data == "confirm":
            await query.edit_message_text("✅ *Confirmed*", parse_mode=ParseMode.MARKDOWN_V2)
            try:
                result = await agent.execute_tool_direct(
                    pending["action"],
                    pending["args"],
                    user_id,
                    signal_handler=telegram_signal_handler,
                    session=session,
                )
                
                # PROXY FIX: Replace the [HITL_PENDING] placeholder with the actual result
                found = False
                for msg in reversed(session.message_history):
                    if msg.get("role") == "tool" and msg.get("tool_call_id") == pending["tool_call_id"]:
                        msg["content"] = result
                        found = True; break
                
                if not found:
                    session.message_history.append({"role": "tool", "tool_call_id": pending["tool_call_id"], "name": pending["action"], "content": result})
                
                # We are already inside the lock, so directly call run_agent_turn instead of process_agent_turn
                # to avoid deadlock
                response = await agent.run_agent_turn(
                    None,
                    session,
                    signal_handler=telegram_signal_handler,
                    memory_service=session_manager.memory,
                )
                await send_long_message(update.effective_chat.id, response, context)
                session_manager.save(user_id)
            except agent.PendingConfirmationError as e:
                await send_confirmation_prompt(e)
                session_manager.save(user_id)
            except Exception:
                logger.exception("Error in confirmed callback flow")
                await context.bot.send_message(update.effective_chat.id, "Tool failed\\.")
                session_manager.save(user_id)
        else:
            await query.edit_message_text("❌ Cancelled")
            # Replace placeholder with denial
            for msg in reversed(session.message_history):
                if msg.get("role") == "tool" and msg.get("tool_call_id") == pending["tool_call_id"]:
                    msg["content"] = "Action denied by user."; break

            try:
                response = await agent.run_agent_turn(
                    None,
                    session,
                    signal_handler=telegram_signal_handler,
                    memory_service=session_manager.memory,
                )
                await send_long_message(update.effective_chat.id, response, context)
                session_manager.save(user_id)
            except agent.PendingConfirmationError as e:
                await send_confirmation_prompt(e)
                session_manager.save(user_id)
            except Exception:
                logger.exception("Error in denied callback flow")
                await context.bot.send_message(update.effective_chat.id, "Tool failed\\.")
                session_manager.save(user_id)


async def send_long_message(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
    """Send message with automatic chunking and Markdown fallback."""
    if not text:
        text = "(No response content)"

    parts = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for part in parts:
        try:
            await context.bot.send_message(
                chat_id, part, parse_mode=ParseMode.MARKDOWN
            )
        except telegram.error.BadRequest as e:
            logger.warning(f"Markdown failed, falling back to plain text: {e}")
            # Clean up potentially broken markdown tags before sending plain text
            plain_text = part.replace("`", "").replace("*", "").replace("_", "")
            await context.bot.send_message(chat_id, plain_text)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")


async def post_init(application: Application) -> None:
    asyncio.create_task(session_manager.auto_expiry_task())
    
    async def notification_worker():
        from tools.database_ops import get_pending_notifications, mark_notified
        while True:
            await asyncio.sleep(10)
            try:
                for tid, uid, obj, stat, res in get_pending_notifications():
                    msg = f"🔔 *Mission Update*\nID: `{tid}`\nObjective: {escape_markdown(obj)}\nStatus: *{stat.upper()}*\n\nResult: {escape_markdown(res)}"
                    try:
                        await application.bot.send_message(chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN_V2)
                    except telegram.error.BadRequest:
                        plain_msg = f"🔔 Mission Update\nID: {tid}\nObjective: {obj}\nStatus: {stat.upper()}\n\nResult: {res}"
                        await application.bot.send_message(chat_id=uid, text=plain_msg)
                    mark_notified(tid)
            except Exception:
                logger.exception("Notification worker loop error")

    async def cron_worker():
        from tools.database_ops import get_due_crons, update_cron_run
        while True:
            await asyncio.sleep(60)
            try:
                for cid, uid, desc, interval in get_due_crons():
                    # Use a dedicated runner for CRON tasks
                    async def run_cron_task(c_id, u_id, d, i):
                        async with session_manager.get_lock(u_id):
                            session = session_manager.get_or_create(u_id)
                            prompt = f"CRON JOB TRIGGERED: {d}"
                            try:
                                response = await agent.run_agent_turn(prompt, session, memory_service=session_manager.memory)
                                msg = f"📅 *Scheduled Task Completed*\n`{escape_markdown(d)}`\n\n{escape_markdown(response)}"
                                try:
                                    await application.bot.send_message(chat_id=u_id, text=msg, parse_mode=ParseMode.MARKDOWN_V2)
                                except telegram.error.BadRequest:
                                    plain_msg = f"📅 Scheduled Task Completed\n{d}\n\n{response}"
                                    await application.bot.send_message(chat_id=u_id, text=plain_msg)
                                session_manager.save(u_id)
                            except agent.PendingConfirmationError as e:
                                keyboard = [[InlineKeyboardButton("✅ Yes", callback_data="confirm"),
                                             InlineKeyboardButton("❌ No", callback_data="deny")]]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                text = f"📅 *Scheduled Task Paused \\(HITL\\)*\n`{escape_markdown(d)}` needs permission:\n`{escape_markdown(e.action)}`"
                                try:
                                    await application.bot.send_message(chat_id=u_id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
                                except telegram.error.BadRequest:
                                    plain_text = f"📅 Scheduled Task Paused (HITL)\n{d} needs permission: {e.action}"
                                    await application.bot.send_message(chat_id=u_id, text=plain_text, reply_markup=reply_markup)
                                session_manager.save(u_id)
                            except Exception as ex:
                                logger.error(f"CRON task {c_id} failed: {ex}")
                                msg = f"❌ *Scheduled Task Failed*\n`{escape_markdown(d)}` error: `{escape_markdown(str(ex))}`"
                                try:
                                    await application.bot.send_message(chat_id=u_id, text=msg, parse_mode=ParseMode.MARKDOWN_V2)
                                except telegram.error.BadRequest:
                                    plain_msg = f"❌ Scheduled Task Failed\n{d} error: {str(ex)}"
                                    await application.bot.send_message(chat_id=u_id, text=plain_msg)

                    asyncio.create_task(run_cron_task(cid, uid, desc, interval))
                    update_cron_run(cid, interval)
            except Exception as e:
                logger.error(f"Cron worker loop error: {e}")

    asyncio.create_task(notification_worker())
    asyncio.create_task(cron_worker())
    await application.bot.set_my_commands([
        BotCommand("start", "Start"), BotCommand("help", "Help"), BotCommand("mode", "Safe/Yolo"),
        BotCommand("think", "Think Mode"),
        BotCommand("tools", "Tools"), BotCommand("experiences", "Technical Lessons"),
        BotCommand("schedules", "Recurring Tasks"), BotCommand("memories", "Memory"), BotCommand("facts", "Auto Facts"),
        BotCommand("forget", "Forget"), BotCommand("get", "Get File"),
        BotCommand("cancel", "Cancel"), BotCommand("status", "Status")
    ])


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and handle exceptions silently to prevent crashes."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(context.error, telegram.error.NetworkError):
        logger.warning(f"Network error (temporary failure): {context.error}")
        return

def main():
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).request(request).build()
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("mode", mode_command))
    application.add_handler(CommandHandler("think", think_command))
    application.add_handler(CommandHandler("tools", tools_command))
    application.add_handler(CommandHandler("experiences", experiences_command))
    application.add_handler(CommandHandler("schedules", schedules_command))
    application.add_handler(CommandHandler("memories", memories_command))
    application.add_handler(CommandHandler("facts", facts_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("get", get_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document_upload))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_upload))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio_upload))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

    if TELEGRAM_USE_WEBHOOK:
        if not TELEGRAM_WEBHOOK_URL_BASE:
            logger.error("TELEGRAM_USE_WEBHOOK=true but TELEGRAM_WEBHOOK_URL is not set.")
            sys.exit(1)

        webhook_url = build_webhook_url(TELEGRAM_WEBHOOK_URL_BASE, TELEGRAM_WEBHOOK_PATH)
        logger.info("Starting Telegram in webhook mode: %s", webhook_url)
        application.run_webhook(
            listen=TELEGRAM_WEBHOOK_LISTEN,
            port=TELEGRAM_WEBHOOK_PORT,
            url_path=TELEGRAM_WEBHOOK_PATH,
            webhook_url=webhook_url,
            secret_token=TELEGRAM_WEBHOOK_SECRET_TOKEN or None,
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
