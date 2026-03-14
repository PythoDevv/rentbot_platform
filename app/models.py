from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class PanelUser(Base):
    __tablename__ = "panel_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    memberships: Mapped[list["BotMembership"]] = relationship(back_populates="user")


class BotTenant(Base):
    __tablename__ = "bot_tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True)
    bot_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    welcome_text: Mapped[str] = mapped_column(
        Text,
        default="Assalomu alaykum. Bot ishga tushdi.",
    )
    menu_button_label: Mapped[str] = mapped_column(
        String(120),
        default="Konkursda qatnashish",
    )
    support_text: Mapped[str] = mapped_column(
        Text,
        default="Admin siz bilan bog'lanadi.",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    memberships: Mapped[list["BotMembership"]] = relationship(back_populates="bot")


class BotMembership(Base):
    __tablename__ = "bot_memberships"
    __table_args__ = (UniqueConstraint("user_id", "bot_id", name="uq_user_bot_membership"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("panel_users.id", ondelete="CASCADE"))
    bot_id: Mapped[int] = mapped_column(ForeignKey("bot_tenants.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(50), default="owner")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user: Mapped[PanelUser] = relationship(back_populates="memberships")
    bot: Mapped[BotTenant] = relationship(back_populates="memberships")
