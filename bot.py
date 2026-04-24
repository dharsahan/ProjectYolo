import asyncio
import base64
import logging
import mimetypes
import os
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

import telegram.error
from colorama import Fore, Style, init
from dotenv import load_dotenv
from openai import AsyncOpenAI
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
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
ENABLE_MEDIA_AI_PIPELINE = (
    os.getenv("ENABLE_MEDIA_AI_PIPELINE", "true").lower() == "true"
)
VISION_MODEL_NAME = os.getenv(
    "VISION_MODEL_NAME", os.getenv("MODEL_NAME", "gpt-4o-mini")
)
TRANSCRIPTION_MODEL_NAME = os.getenv(
    "TRANSCRIPTION_MODEL_NAME", "gpt-4o-mini-transcribe"
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

TELEGRAM_USE_WEBHOOK = os.getenv("TELEGRAM_USE_WEBHOOK", "false").lower() == "true"
TELEGRAM_WEBHOOK_LISTEN = os.getenv("TELEGRAM_WEBHOOK_LISTEN", "0.0.0.0")
TELEGRAM_WEBHOOK_PORT = _get_int_env("TELEGRAM_WEBHOOK_PORT", 8080)
TELEGRAM_WEBHOOK_PATH = (
    os.getenv("TELEGRAM_WEBHOOK_PATH", "telegram").strip().strip("/")
)
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
    status_msg_id: Optional[int] = None
    stream_msg_id: Optional[int] = None
    last_stream_time = 0.0

    async def telegram_signal_handler(signal_str: str) -> Optional[str]:
        nonlocal status_msg_id, stream_msg_id, last_stream_time

        if signal_str.startswith("__SEND_FILE__:"):
            file_path = signal_str.replace("__SEND_FILE__:", "")
            try:
                with open(file_path, "rb") as doc:
                    await context.bot.send_document(chat_id=chat_id, document=doc)
                return f"File `{os.path.basename(file_path)}` uploaded successfully."
            except Exception as e:
                return f"Failed to upload file: {e}"

        if signal_str.startswith("__STATUS__:"):
            status_text = signal_str.replace("__STATUS__:", "").strip()
            if not status_text:
                if status_msg_id:
                    try:
                        await context.bot.delete_message(
                            chat_id=chat_id, message_id=status_msg_id
                        )
                    except Exception:
                        pass
                    status_msg_id = None
                return None

            text = f"⏳ *Agent Status*\n_{escape_markdown(status_text)}_"
            try:
                if status_msg_id:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                else:
                    msg = await context.bot.send_message(
                        chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2
                    )
                    status_msg_id = msg.message_id
            except Exception:
                # Fallback if edit fails (e.g. content same)
                try:
                    msg = await context.bot.send_message(
                        chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2
                    )
                    status_msg_id = msg.message_id
                except Exception:
                    pass
            return None

        if signal_str.startswith("__STREAM__:"):
            content = signal_str.replace("__STREAM__:", "")
            if not content:
                return None

            now = time.time()
            # Throttle stream updates to avoid Telegram rate limits (1.2s interval)
            if stream_msg_id and (now - last_stream_time < 1.2):
                return None

            if len(content) > 4000:
                content = content[:4000] + "...\n[Streaming paused due to length limit]"

            try:
                if stream_msg_id:
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=stream_msg_id, text=content + " ✍️"
                    )
                else:
                    msg = await context.bot.send_message(
                        chat_id=chat_id, text=content + " ✍️"
                    )
                    stream_msg_id = msg.message_id
                last_stream_time = now
            except Exception:
                pass
            return None

        if signal_str.startswith("__STREAM_END__:"):
            if stream_msg_id:
                try:
                    await context.bot.delete_message(
                        chat_id=chat_id, message_id=stream_msg_id
                    )
                except Exception:
                    pass
                stream_msg_id = None
            return None

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


def guess_file_extension(
    file_name: Optional[str], mime_type: Optional[str], default_ext: str
) -> str:
    if file_name and Path(file_name).suffix:
        return Path(file_name).suffix
    if mime_type:
        guessed = mimetypes.guess_extension(mime_type)
        if guessed:
            return guessed
    return default_ext


async def maybe_extract_image_text(
    image_path: Path, mime_type: Optional[str]
) -> Optional[str]:
    if MEDIA_AI_CLIENT is None:
        return None
    if not image_path.exists():
        return None
    if image_path.stat().st_size > MAX_MEDIA_AI_BYTES:
        return None

    effective_mime = (
        mime_type or mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    )
    try:
        # Performance: read file off the event loop. Photos can be many MB and
        # base64-encoding plus disk I/O on the loop blocks all other coroutines.
        image_bytes = await asyncio.to_thread(image_path.read_bytes)
        b64 = await asyncio.to_thread(
            lambda: base64.b64encode(image_bytes).decode("ascii")
        )
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
        # Performance: offload disk read so the event loop stays responsive
        # while the audio file (potentially many MB) is loaded.
        audio_bytes = await asyncio.to_thread(audio_path.read_bytes)
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
    assert update.effective_user is not None
    user_id = update.effective_user.id
    log_bot(
        user_id, "UPLOAD", f"Saved `{relative_path}` ({file_size} bytes)", Fore.GREEN
    )

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
            prompt_parts.append(f"{extracted_label} preview:\n{extracted_text[:1200]}")
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
    assert update.message is not None
    await update.message.reply_text("\n".join(reply_lines))


async def auth_check(update: Update) -> bool:
    """Check if the user is authorized. Silently ignore if not."""
    assert update.effective_user is not None
    user_id = update.effective_user.id if update.effective_user else None
    if user_id not in ALLOWED_USER_IDS:
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    assert update.effective_user is not None
    user_id = update.effective_user.id
    session_manager.clear(user_id)
    log_bot(user_id, "IN", "/start", Fore.CYAN)

    welcome = (
        "*Welcome to Yolo\\!*\n\n"
    )
    assert update.message is not None
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN_V2)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    assert update.effective_user is not None
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
    assert update.message is not None
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)


async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    if not update.message or not update.message.document:
        return

    assert update.effective_user is not None

    assert update.effective_user
    user_id = update.effective_user.id
    document = update.message.document
    file_size = int(document.file_size or 0)

    if file_size > MAX_TELEGRAM_UPLOAD_BYTES:
        assert update.message is not None
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
        assert update.message is not None
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

    assert update.effective_user is not None

    user_id = update.effective_user.id
    photo_sizes = update.message.photo
    photo = photo_sizes[-1]
    file_size = int(photo.file_size or 0)

    if file_size > MAX_TELEGRAM_UPLOAD_BYTES:
        assert update.message is not None
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
        assert update.message is not None
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
    log_bot(
        user_id,
        "UPLOAD",
        f"Saved photo `{local_path.name}` ({file_size} bytes)",
        Fore.GREEN,
    )


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
        media = update.message.audio  # type: ignore
        media_kind = "audio"
        default_ext = ".mp3"

    if media is None:
        return

    file_size = int(getattr(media, "file_size", 0) or 0)
    if file_size > MAX_TELEGRAM_UPLOAD_BYTES:
        assert update.message is not None
        await update.message.reply_text(
            f"Upload rejected: {media_kind} is too large ({file_size} bytes). "
            f"Limit is {MAX_TELEGRAM_UPLOAD_BYTES} bytes."
        )
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_name = getattr(media, "file_name", None)
    mime_type = getattr(media, "mime_type", None)
    ext = guess_file_extension(file_name, mime_type, default_ext)
    safe_name = safe_upload_filename(
        file_name, f"{media_kind}_{media.file_unique_id}{ext}"
    )
    local_path = get_uploads_dir() / f"{timestamp}_{safe_name}"

    try:
        tg_file = await context.bot.get_file(media.file_id)
        await tg_file.download_to_drive(custom_path=str(local_path))
    except Exception as e:
        logger.exception("Failed to download uploaded audio/voice")
        assert update.message is not None
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
    assert update.effective_user is not None
    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    log_bot(user_id, "IN", "/cancel", Fore.CYAN)

    if session.pending_confirmations:
        for p in session.pending_confirmations:
            session.message_history.append(
                {
                    "role": "tool",
                    "tool_call_id": p["tool_call_id"],
                    "name": p["action"],
                    "content": "Action denied by user.",
                }
            )
        session.history_dirty = True
        count = len(session.pending_confirmations)
        session.pending_confirmations = []
        session_manager.save(user_id)
        assert update.message is not None
        await update.message.reply_text(
            f"{count} pending actions cancelled\\.", parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        assert update.message is not None
        await update.message.reply_text("No pending actions\\.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    assert update.effective_user is not None
    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    log_bot(user_id, "IN", "/status", Fore.CYAN)

    history_len = len(session.message_history)
    compact_threshold = agent.AUTO_COMPACT_THRESHOLD
    pending_count = len(session.pending_confirmations)
    has_pending = f"Yes ({pending_count})" if pending_count > 0 else "No"
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
        f"• History: `{history_len}/{compact_threshold}` messages\n"
        f"• Confirmations pending: *{has_pending}*\n"
        f"• Sandbox: `{sandbox_path}`\n"
        f"• LLM calls: `{getattr(session, 'llm_call_count', 0)}`\n"
        f"• Tokens: `{getattr(session, 'total_tokens', 0)}` "
        f"\\(prompt: `{getattr(session, 'total_prompt_tokens', 0)}` "
        f"\\+ completion: `{getattr(session, 'total_completion_tokens', 0)}`\\)"
    )
    assert update.message is not None
    await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN_V2)


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    assert update.effective_user is not None
    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    args = context.args
    if not args:
        current = "Yolo" if session.yolo_mode else "Safe"
        assert update.message is not None
        await update.message.reply_text(
            f"Current mode: *{current}*\\. Use `/mode yolo` or `/mode safe`\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    choice = args[0].lower()
    if choice == "yolo":
        session.yolo_mode = True
        assert update.message is not None
        await update.message.reply_text(
            "⚡ *YOLO Mode Enabled*\\!", parse_mode=ParseMode.MARKDOWN_V2
        )
    elif choice == "safe":
        session.yolo_mode = False
        assert update.message is not None
        await update.message.reply_text(
            "🛡️ *Safe Mode Enabled*", parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        assert update.message is not None
        await update.message.reply_text(
            "Unknown mode\\. Use `/mode yolo` or `/mode safe`\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    session_manager.save(user_id)


async def think_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return

    assert update.effective_user is not None

    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    args = context.args

    if not args:
        current = "On" if session.think_mode else "Off"
        policy = getattr(session, "think_mode_policy", "auto")
        assert update.message is not None
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
        assert update.message is not None
        await update.message.reply_text(
            "🧠 *Think Mode Enabled*\\. Policy set to *force_on*\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if choice in {"off", "false", "0", "disable", "disabled"}:
        session.think_mode_policy = "force_off"
        session.think_mode = False
        session_manager.save(user_id)
        assert update.message is not None
        await update.message.reply_text(
            "⚙️ *Think Mode Disabled*\\. Policy set to *force_off*\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if choice in {"auto", "smart", "default"}:
        session.think_mode_policy = "auto"
        session.think_mode = False
        session_manager.save(user_id)
        assert update.message is not None
        await update.message.reply_text(
            "🤖 *Think Mode Auto* enabled\\. I will turn think mode on for complex tasks automatically\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    assert update.message is not None

    await update.message.reply_text(
        "Unknown option\\. Use `/think on`, `/think off`, or `/think auto`\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def compact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    assert update.effective_user is not None
    user_id = update.effective_user.id
    session = session_manager.get_or_create(user_id)
    log_bot(user_id, "CMD", "/compact")

    async with session_manager.get_lock(user_id):
        await agent._compact_history(session, agent.router)
        session_manager.save(user_id)
        assert update.message is not None
        await update.message.reply_text(
            "Conversation history compacted. Check `/status`."
        )


async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    import tools

    tools_list = "*Available Tools:*\n\n"
    for tool_schema in tools.TOOLS_SCHEMAS:
        name = escape_markdown(tool_schema["function"]["name"])  # type: ignore
        desc = escape_markdown(tool_schema["function"]["description"])  # type: ignore
        tools_list += f"• `{name}`: {desc}\n"
    await send_long_message((update.effective_chat.id if update.effective_chat else 0), tools_list, context)


async def experiences_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all technical lessons learned."""
    if not await auth_check(update):
        return
    assert update.effective_user is not None
    user_id = update.effective_user.id
    log_bot(user_id, "IN", "/experiences", Fore.CYAN)

    try:
        from tools.experience_ops import list_experiences

        result = list_experiences(user_id)
        await send_long_message((update.effective_chat.id if update.effective_chat else 0), result, context)
    except Exception as e:
        assert update.message is not None
        await update.message.reply_text(f"Error: {e}")


async def schedules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List active scheduled tasks."""
    if not await auth_check(update):
        return
    assert update.effective_user is not None
    user_id = update.effective_user.id
    log_bot(user_id, "IN", "/schedules", Fore.CYAN)

    try:
        from tools.cron_ops import get_scheduled_tasks

        result = get_scheduled_tasks(user_id)
        await send_long_message((update.effective_chat.id if update.effective_chat else 0), result, context)
    except Exception as e:
        assert update.message is not None
        await update.message.reply_text(f"Error: {e}")


async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    assert update.effective_user is not None
    user_id = update.effective_user.id
    log_bot(user_id, "IN", "/memories", Fore.CYAN)

    try:
        from tools.memory_ops import memory_list

        result = memory_list(user_id)
        await send_long_message((update.effective_chat.id if update.effective_chat else 0), result, context)
    except Exception as e:
        assert update.message is not None
        await update.message.reply_text(f"Error: {e}")


async def facts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    assert update.effective_user is not None
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

        if (
            not session.message_history
            or session.message_history[0].get("role") != "system"
        ):
            assert update.message is not None
            await update.message.reply_text("No system prompt found for this session.")
            return

        content = str(session.message_history[0].get("content") or "")
        facts_list = list(agent.extract_auto_basic_facts(content))
        if not facts_list:
            assert update.message is not None
            await update.message.reply_text("No auto basic facts are currently injected.")
            return
        lines = [f"{i+1}. {fact}" for i, fact in enumerate(facts_list)]
        if not facts_list:
            assert update.message is not None
            await update.message.reply_text(
                "No auto basic facts are currently injected."
            )
            return

        lines = [f"{i+1}. {fact}" for i, fact in enumerate(facts_list)]
        await send_long_message(
            (update.effective_chat.id if update.effective_chat else 0),
            "### Auto Basic Facts\n\n" + "\n".join(lines),
            context,
        )
    except Exception as e:
        assert update.message is not None
        await update.message.reply_text(f"Error: {e}")


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    assert update.effective_user is not None
    user_id = update.effective_user.id
    log_bot(user_id, "IN", "/forget", Fore.CYAN)

    try:
        from tools.memory_ops import memory_wipe

        result = memory_wipe(user_id)
        assert update.message is not None
        await update.message.reply_text(result)
    except Exception as e:
        assert update.message is not None
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
                await context.bot.send_document(
                    chat_id=(update.effective_chat.id if update.effective_chat else 0), document=doc
                )
        else:
            assert update.message is not None
            await update.message.reply_text("Error: path is not a file.")
    except Exception as e:
        assert update.message is not None
        await update.message.reply_text(f"Error: {e}")


async def process_agent_turn(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: Optional[str]
):
    assert update.effective_user is not None
    user_id = update.effective_user.id

    async with session_manager.get_lock(user_id):
        session = session_manager.get_or_create(user_id)
        assert update.effective_chat is not None
        chat_id = (update.effective_chat.id if update.effective_chat else 0)
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
        except agent.PendingConfirmationError:
            # We have one or more pending confirmations in session.pending_confirmations
            count = len(session.pending_confirmations)
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm All", callback_data="confirm_all"),
                    InlineKeyboardButton("❌ Deny All", callback_data="deny_all"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            lines = [f"⚠️ *{count} Actions Pending Confirmation*"]
            for i, p in enumerate(session.pending_confirmations):
                lines.append(
                    f"{i+1}\\. `{escape_markdown(p['action'])}` on `{escape_markdown(p['path'])}`"
                )

            assert update.message is not None

            await update.message.reply_text(
                "\n".join(lines),
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            session_manager.save(user_id)
        except Exception:
            logger.exception("Error in process_agent_turn")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    assert update.effective_user is not None
    user_id = update.effective_user.id
    # Check pending confirmations outside the lock
    session = session_manager.get_or_create(user_id)
    if session.pending_confirmations:
        assert update.message is not None
        await update.message.reply_text(
            f"Pending confirmations required ({len(session.pending_confirmations)} tasks)\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    assert update.message
    await process_agent_turn(update, context, update.message.text)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        return
    query = update.callback_query
    assert query is not None
    await query.answer()
    assert update.effective_user is not None
    user_id = update.effective_user.id

    async def _safe_edit_callback_message(text: str) -> None:
        """Best-effort status update for callback cards with graceful fallback."""
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            logger.exception("Failed to edit callback message")
            try:
                await context.bot.send_message(
                    (update.effective_chat.id if update.effective_chat else 0),
                    text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except Exception:
                logger.exception("Failed to send callback fallback message")

    async with session_manager.get_lock(user_id):
        session = session_manager.get_or_create(user_id)
        if not session.pending_confirmations:
            await _safe_edit_callback_message("ℹ️ *No Pending Actions*")
            return

        telegram_signal_handler = build_telegram_signal_handler(
            context, (update.effective_chat.id if update.effective_chat else 0)
        )

        async def send_confirmation_prompt(count: int, confirmations: list):
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm All", callback_data="confirm_all"),
                    InlineKeyboardButton("❌ Deny All", callback_data="deny_all"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            lines = [f"⚠️ *{count} Actions Pending Confirmation*"]
            for i, p in enumerate(confirmations):
                lines.append(
                    f"{i+1}\\. `{escape_markdown(p['action'])}` on `{escape_markdown(p['path'])}`"
                )

            await context.bot.send_message(
                chat_id=(update.effective_chat.id if update.effective_chat else 0),
                text="\n".join(lines),
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2,
            )

        pending_list = list(session.pending_confirmations)
        session.pending_confirmations = []

        if query.data == "confirm_all":
            await _safe_edit_callback_message("✅ *All Actions Confirmed*")
            try:
                # Execute all pending in parallel
                execution_tasks = []
                for p in pending_list:
                    execution_tasks.append(
                        agent.execute_tool_direct(
                            p["action"],
                            p["args"],
                            user_id,
                            signal_handler=telegram_signal_handler,
                            session=session,
                        )
                    )

                results = await asyncio.gather(*execution_tasks)

                # Update history for each
                for p, result in zip(pending_list, results):
                    found = False
                    for msg in reversed(session.message_history):
                        if (
                            msg.get("role") == "tool"
                            and msg.get("tool_call_id") == p["tool_call_id"]
                        ):
                            msg["content"] = result
                            found = True
                            break
                    if not found:
                        session.message_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": p["tool_call_id"],
                                "name": p["action"],
                                "content": result,
                            }
                        )
                session.history_dirty = True

                response = await agent.run_agent_turn(
                    None,
                    session,
                    signal_handler=telegram_signal_handler,
                    memory_service=session_manager.memory,
                )
                await send_long_message((update.effective_chat.id if update.effective_chat else 0), response, context)
                session_manager.save(user_id)
            except agent.PendingConfirmationError:
                await send_confirmation_prompt(
                    len(session.pending_confirmations), session.pending_confirmations
                )
                session_manager.save(user_id)
            except Exception:
                logger.exception("Error in confirm_all callback flow")
                await context.bot.send_message(
                    (update.effective_chat.id if update.effective_chat else 0), "One or more tools failed\\."
                )
                session_manager.save(user_id)
        else:
            await _safe_edit_callback_message("❌ *All Actions Cancelled*")
            for p in pending_list:
                for msg in reversed(session.message_history):
                    if (
                        msg.get("role") == "tool"
                        and msg.get("tool_call_id") == p["tool_call_id"]
                    ):
                        msg["content"] = "Action denied by user."
                        break
            session.history_dirty = True

            try:
                response = await agent.run_agent_turn(
                    None,
                    session,
                    signal_handler=telegram_signal_handler,
                    memory_service=session_manager.memory,
                )
                await send_long_message((update.effective_chat.id if update.effective_chat else 0), response, context)
                session_manager.save(user_id)
            except agent.PendingConfirmationError:
                await send_confirmation_prompt(
                    len(session.pending_confirmations), session.pending_confirmations
                )
                session_manager.save(user_id)
            except Exception:
                logger.exception("Error in deny_all callback flow")
                await context.bot.send_message(
                    (update.effective_chat.id if update.effective_chat else 0), "Turn failed after denial\\."
                )
                session_manager.save(user_id)


async def send_long_message(
    chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE
):
    """Send message with automatic chunking and Markdown fallback."""
    if not text:
        text = "(No response content)"

    parts = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for part in parts:
        markdown_sent = False
        try:
            await context.bot.send_message(chat_id, part, parse_mode=ParseMode.MARKDOWN)
            markdown_sent = True
        except telegram.error.RetryAfter as e:
            retry_after = getattr(e, "retry_after", 1)
            delay = (
                max(1.0, float(retry_after.total_seconds()))
                if hasattr(retry_after, "total_seconds")
                else max(1.0, float(retry_after))
            )
            logger.warning(
                "Flood control for chat_id=%s, waiting %.1fs before retry",
                chat_id,
                delay,
            )
            await asyncio.sleep(delay)
            try:
                await context.bot.send_message(
                    chat_id, part, parse_mode=ParseMode.MARKDOWN
                )
                markdown_sent = True
            except Exception as retry_error:
                logger.warning(f"Retry send failed, trying plain text fallback: {retry_error}")
        except telegram.error.BadRequest as e:
            logger.warning(f"Markdown failed, falling back to plain text: {e}")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

        if markdown_sent:
            continue

        # Clean up potentially broken markdown tags before sending plain text.
        plain_text = part.replace("`", "").replace("*", "").replace("_", "")
        try:
            await context.bot.send_message(chat_id, plain_text)
        except telegram.error.RetryAfter as e:
            retry_after = getattr(e, "retry_after", 1)
            delay = (
                max(1.0, float(retry_after.total_seconds()))
                if hasattr(retry_after, "total_seconds")
                else max(1.0, float(retry_after))
            )
            logger.warning(
                "Flood control on plain fallback for chat_id=%s, waiting %.1fs before retry",
                chat_id,
                delay,
            )
            await asyncio.sleep(delay)
            try:
                await context.bot.send_message(chat_id, plain_text)
            except Exception as retry_plain_error:
                logger.error(f"Failed to send plain text after retry: {retry_plain_error}")
        except Exception as plain_error:
            logger.error(f"Failed to send plain text message: {plain_error}")


async def post_init(application: Application) -> None:
    asyncio.create_task(session_manager.auto_expiry_task())

    async def notification_worker():
        from tools.database_ops import get_pending_notifications, mark_notified

        # Adaptive backoff: poll fast (10s) when notifications were just seen,
        # back off to 60s when idle. Saves DB queries + event-loop wakeups.
        idle_sleep = 60
        active_sleep = 10
        sleep_for = active_sleep
        while True:
            await asyncio.sleep(sleep_for)
            try:
                pending = get_pending_notifications()
                if not pending:
                    sleep_for = idle_sleep
                    continue
                sleep_for = active_sleep
                for tid, uid, obj, stat, res in pending:
                    # Split result into safe chunks. objective/formatting add ~500 chars, so 3000 is safe.
                    res_parts = [res[i : i + 3000] for i in range(0, len(res), 3000)]
                    delivered = False

                    for idx, r_part in enumerate(res_parts):
                        suffix = (
                            f" (Part {idx+1}/{len(res_parts)})"
                            if len(res_parts) > 1
                            else ""
                        )
                        msg = f"🔔 *Mission Update*{suffix}\nID: `{tid}`\nObjective: {escape_markdown(obj)}\nStatus: *{stat.upper()}*\n\nResult: {escape_markdown(r_part)}"
                        try:
                            await application.bot.send_message(
                                chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN_V2
                            )
                            delivered = True
                        except telegram.error.BadRequest as e:
                            # Markdown parse errors or length issues are recoverable via plain text fallback.
                            plain_msg = f"🔔 Mission Update{suffix}\nID: {tid}\nObjective: {obj}\nStatus: {stat.upper()}\n\nResult: {r_part}"
                            if len(plain_msg) > 4080:
                                plain_msg = plain_msg[:4000] + "..."

                            try:
                                await application.bot.send_message(
                                    chat_id=uid, text=plain_msg
                                )
                                delivered = True
                            except telegram.error.BadRequest as plain_err:
                                if "chat not found" in str(plain_err).lower():
                                    logger.warning(
                                        "Skipping notification for unknown chat_id=%s task_id=%s",
                                        uid,
                                        tid,
                                    )
                                    delivered = True
                                    break
                                logger.exception(
                                    "Notification delivery failed with BadRequest for task_id=%s",
                                    tid,
                                )
                            except telegram.error.Forbidden:
                                logger.warning(
                                    "Skipping notification for forbidden chat_id=%s task_id=%s",
                                    uid,
                                    tid,
                                )
                                delivered = True
                                break
                        except telegram.error.Forbidden:
                            logger.warning(
                                "Skipping notification for forbidden chat_id=%s task_id=%s",
                                uid,
                                tid,
                            )
                            delivered = True
                            break
                        except telegram.error.TelegramError:
                            logger.exception(
                                "Transient telegram error while notifying task_id=%s",
                                tid,
                            )

                    if delivered:
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
                                response = await agent.run_agent_turn(
                                    prompt,
                                    session,
                                    memory_service=session_manager.memory,
                                )
                                msg = f"📅 *Scheduled Task Completed*\n`{escape_markdown(d)}`\n\n{escape_markdown(response)}"
                                try:
                                    await application.bot.send_message(
                                        chat_id=u_id,
                                        text=msg,
                                        parse_mode=ParseMode.MARKDOWN_V2,
                                    )
                                except telegram.error.BadRequest:
                                    plain_msg = f"📅 Scheduled Task Completed\n{d}\n\n{response}"
                                    await application.bot.send_message(
                                        chat_id=u_id, text=plain_msg
                                    )
                                session_manager.save(u_id)
                            except agent.PendingConfirmationError as e:
                                keyboard = [
                                    [
                                        InlineKeyboardButton(
                                            "✅ Yes", callback_data="confirm"
                                        ),
                                        InlineKeyboardButton(
                                            "❌ No", callback_data="deny"
                                        ),
                                    ]
                                ]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                text = f"📅 *Scheduled Task Paused \\(HITL\\)*\n`{escape_markdown(d)}` needs permission:\n`{escape_markdown(e.action)}`"
                                try:
                                    await application.bot.send_message(
                                        chat_id=u_id,
                                        text=text,
                                        reply_markup=reply_markup,
                                        parse_mode=ParseMode.MARKDOWN_V2,
                                    )
                                except telegram.error.BadRequest:
                                    plain_text = f"📅 Scheduled Task Paused (HITL)\n{d} needs permission: {e.action}"
                                    await application.bot.send_message(
                                        chat_id=u_id,
                                        text=plain_text,
                                        reply_markup=reply_markup,
                                    )
                                session_manager.save(u_id)
                            except Exception as ex:
                                logger.error(f"CRON task {c_id} failed: {ex}")
                                msg = f"❌ *Scheduled Task Failed*\n`{escape_markdown(d)}` error: `{escape_markdown(str(ex))}`"
                                try:
                                    await application.bot.send_message(
                                        chat_id=u_id,
                                        text=msg,
                                        parse_mode=ParseMode.MARKDOWN_V2,
                                    )
                                except telegram.error.BadRequest:
                                    plain_msg = f"❌ Scheduled Task Failed\n{d} error: {str(ex)}"
                                    await application.bot.send_message(
                                        chat_id=u_id, text=plain_msg
                                    )

                    asyncio.create_task(run_cron_task(cid, uid, desc, interval))
                    update_cron_run(cid, interval)
            except Exception as e:
                logger.error(f"Cron worker loop error: {e}")

    asyncio.create_task(notification_worker())
    asyncio.create_task(cron_worker())
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Start"),
            BotCommand("help", "Help"),
            BotCommand("mode", "Safe/Yolo"),
            BotCommand("think", "Think Mode"),
            BotCommand("compact", "Compact History"),
            BotCommand("tools", "Tools"),
            BotCommand("experiences", "Technical Lessons"),
            BotCommand("schedules", "Recurring Tasks"),
            BotCommand("memories", "Memory"),
            BotCommand("facts", "Auto Facts"),
            BotCommand("forget", "Forget"),
            BotCommand("get", "Get File"),
            BotCommand("cancel", "Cancel"),
            BotCommand("status", "Status"),
        ]
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and handle exceptions silently to prevent crashes."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(context.error, telegram.error.NetworkError):
        logger.warning(f"Network error (temporary failure): {context.error}")
        return


def main():
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    application = (
        ApplicationBuilder().token(TOKEN).post_init(post_init).request(request).build()
    )
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("compact", compact_command))
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
    application.add_handler(
        MessageHandler(filters.Document.ALL, handle_document_upload)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_upload))
    application.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, handle_audio_upload)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(CallbackQueryHandler(handle_callback))

    if TELEGRAM_USE_WEBHOOK:
        if not TELEGRAM_WEBHOOK_URL_BASE:
            logger.error(
                "TELEGRAM_USE_WEBHOOK=true but TELEGRAM_WEBHOOK_URL is not set."
            )
            sys.exit(1)

        webhook_url = build_webhook_url(
            TELEGRAM_WEBHOOK_URL_BASE, TELEGRAM_WEBHOOK_PATH
        )
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

