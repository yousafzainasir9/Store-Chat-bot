"""SQLAlchemy (async, Postgres) conversation repository.

Lazily imported by the composition root only when ``DATABASE_URL`` is set, so the
offline test suite never needs SQLAlchemy wired. Tables are created on first use
for convenience in dev; production uses Alembic migrations (``backend/migrations``).
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.conversation import Conversation, Feedback, MessageRole, StoredMessage


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    locale: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[str] = mapped_column(Text, default="[]")  # JSON-encoded
    handoff_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedbackRow(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    message_id: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(String(8))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SqlConversationRepository:
    """Postgres-backed conversation repository."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_async_engine(database_url, future=True)
        self._session: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )
        self._initialized = False

    async def _ensure_schema(self) -> None:
        if self._initialized:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._initialized = True

    async def get_or_create(self, conversation_id: str, *, locale: str = "en") -> Conversation:
        await self._ensure_schema()
        async with self._session() as session:
            row = await session.get(ConversationRow, conversation_id)
            if row is None:
                conv = Conversation(id=conversation_id, locale=locale)
                session.add(
                    ConversationRow(id=conv.id, locale=conv.locale, created_at=conv.created_at)
                )
                await session.commit()
                return conv
            return Conversation(id=row.id, locale=row.locale, created_at=row.created_at)

    async def add_message(self, message: StoredMessage) -> None:
        await self._ensure_schema()
        async with self._session() as session:
            session.add(
                MessageRow(
                    id=message.id,
                    conversation_id=message.conversation_id,
                    role=message.role.value,
                    content=message.content,
                    citations=json.dumps(message.citations),
                    handoff_reason=message.handoff_reason,
                    confidence=message.confidence,
                    token_count=message.token_count,
                    created_at=message.created_at,
                )
            )
            await session.commit()

    async def get(self, conversation_id: str) -> Conversation | None:
        await self._ensure_schema()
        async with self._session() as session:
            row = await session.get(ConversationRow, conversation_id)
            if row is None:
                return None
            result = await session.execute(
                select(MessageRow)
                .where(MessageRow.conversation_id == conversation_id)
                .order_by(MessageRow.created_at)
            )
            messages = [
                StoredMessage(
                    id=m.id,
                    conversation_id=m.conversation_id,
                    role=MessageRole(m.role),
                    content=m.content,
                    citations=json.loads(m.citations),
                    handoff_reason=m.handoff_reason,
                    confidence=m.confidence,
                    token_count=m.token_count,
                    created_at=m.created_at,
                )
                for m in result.scalars()
            ]
            return Conversation(
                id=row.id, locale=row.locale, created_at=row.created_at, messages=messages
            )

    async def list_conversations(self, *, limit: int = 100) -> list[Conversation]:
        await self._ensure_schema()
        async with self._session() as session:
            result = await session.execute(
                select(ConversationRow).order_by(ConversationRow.created_at.desc()).limit(limit)
            )
            convs: list[Conversation] = []
            for row in result.scalars():
                full = await self.get(row.id)
                if full is not None:
                    convs.append(full)
            return convs

    async def delete_conversation(self, conversation_id: str) -> bool:
        await self._ensure_schema()
        async with self._session() as session:
            row = await session.get(ConversationRow, conversation_id)
            if row is None:
                return False
            await session.execute(
                delete(MessageRow).where(MessageRow.conversation_id == conversation_id)
            )
            await session.execute(
                delete(FeedbackRow).where(FeedbackRow.conversation_id == conversation_id)
            )
            await session.delete(row)
            await session.commit()
            return True

    async def purge_older_than(self, cutoff: datetime) -> int:
        await self._ensure_schema()
        async with self._session() as session:
            result = await session.execute(
                select(ConversationRow.id).where(ConversationRow.created_at < cutoff)
            )
            ids = list(result.scalars())
        for cid in ids:
            await self.delete_conversation(cid)
        return len(ids)

    async def add_feedback(self, feedback: Feedback) -> None:
        await self._ensure_schema()
        async with self._session() as session:
            session.add(
                FeedbackRow(
                    id=feedback.id,
                    conversation_id=feedback.conversation_id,
                    message_id=feedback.message_id,
                    value=feedback.value,
                    comment=feedback.comment,
                    created_at=feedback.created_at,
                )
            )
            await session.commit()

    async def list_feedback(self) -> list[Feedback]:
        await self._ensure_schema()
        async with self._session() as session:
            result = await session.execute(select(FeedbackRow).order_by(FeedbackRow.created_at))
            return [
                Feedback(
                    id=f.id,
                    conversation_id=f.conversation_id,
                    message_id=f.message_id,
                    value=f.value,
                    comment=f.comment,
                    created_at=f.created_at,
                )
                for f in result.scalars()
            ]
