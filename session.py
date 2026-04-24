import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any,
    Dict,
    List,
    Optional,
)  # noqa: F401  (Optional used in dataclass annotations)

from tools.database_ops import init_db, load_session, save_session


@dataclass
class Session:
    user_id: int
    message_history: List[Dict[str, Any]] = field(default_factory=list)
    pending_confirmations: List[Dict[str, Any]] = field(default_factory=list)
    yolo_mode: bool = False
    think_mode: bool = False
    think_mode_policy: str = "auto"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Performance: track whether history needs sanitization. Set by `mark_dirty()`
    # whenever history is mutated; cleared after sanitize. Avoids O(n) rescan
    # on every LLM round when nothing changed.
    history_dirty: bool = True
    # Performance: hash of last persisted history payload, used to skip
    # redundant SQLite writes when save() is called multiple times per turn
    # (callbacks, status updates, etc.) without intervening changes.
    last_saved_signature: Optional[int] = None
    # Token / cost tracking – accumulated across the session lifetime.
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    llm_call_count: int = 0

    def mark_dirty(self) -> None:
        self.history_dirty = True


class SessionManager:
    def __init__(self, timeout_minutes: int = 60):
        self.sessions: Dict[int, Session] = {}
        self.locks: Dict[int, asyncio.Lock] = {}
        self.timeout_minutes = timeout_minutes

        # Ensure DB is ready
        init_db()

        # Use the global shared memory instance
        from tools.memory_service import get_memory

        self.memory = get_memory()

    def get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self.locks:
            self.locks[user_id] = asyncio.Lock()
        return self.locks[user_id]

    def get_or_create(self, user_id: int) -> Session:
        if user_id not in self.sessions:
            # Try to load from DB first
            history, yolo_mode, think_mode, think_mode_policy, pending_confirmations = (
                load_session(user_id)
            )
            if history is not None:
                self.sessions[user_id] = Session(
                    user_id=user_id,
                    message_history=history,
                    pending_confirmations=pending_confirmations or [],
                    yolo_mode=yolo_mode,
                    think_mode=think_mode,
                    think_mode_policy=think_mode_policy or "auto",
                )
            else:
                self.sessions[user_id] = Session(user_id=user_id)

        session = self.sessions[user_id]
        session.last_active = datetime.now(timezone.utc)
        return session

    def save(self, user_id: int, force: bool = False):
        """Save a specific session to the database.

        Performance: computes a cheap signature of the relevant state and
        skips the write when nothing has changed since the previous save.
        This eliminates redundant full-history JSON re-serialization on the
        hot path (multiple `save()` calls per turn from bot callbacks).
        Pass `force=True` to bypass the cache (e.g., on shutdown/expiry).
        """
        if user_id not in self.sessions:
            return
        session = self.sessions[user_id]

        # Cheap signature: history length + last message identity + flags +
        # pending confirmations count. This catches all real mutations without
        # serializing the entire history just to hash it.
        last_msg_id = id(session.message_history[-1]) if session.message_history else 0
        signature = hash(
            (
                len(session.message_history),
                last_msg_id,
                session.yolo_mode,
                session.think_mode,
                session.think_mode_policy,
                len(session.pending_confirmations),
            )
        )
        if not force and signature == session.last_saved_signature:
            return

        save_session(
            user_id,
            session.message_history,
            session.yolo_mode,
            session.think_mode,
            session.think_mode_policy,
            session.pending_confirmations,
        )
        session.last_saved_signature = signature

    def clear(self, user_id: int):
        if user_id in self.sessions:
            del self.sessions[user_id]
        if user_id in self.locks:
            del self.locks[user_id]
        # Also clear from DB for a true reset
        from tools.database_ops import save_session as db_save

        db_save(user_id, [], False, False, "auto", None)

    async def auto_expiry_task(self):
        """Background task to remove expired sessions from memory (but keep in DB)."""
        while True:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            expired_ids = [
                uid
                for uid, sess in self.sessions.items()
                if (now - sess.last_active).total_seconds() > self.timeout_minutes * 60
            ]
            for uid in expired_ids:
                # Save to DB before dropping from memory (force to bypass dedup cache)
                self.save(uid, force=True)
                del self.sessions[uid]
                if uid in self.locks:
                    del self.locks[uid]
