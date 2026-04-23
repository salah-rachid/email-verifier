from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import Computed
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Text
from sqlalchemy import func
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("credits >= 0", name="ck_users_credits_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
        server_default=text("encode(gen_random_bytes(24), 'hex')"),
    )
    credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("100"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("total_emails >= 0", name="ck_jobs_total_emails_non_negative"),
        CheckConstraint("processed >= 0", name="ck_jobs_processed_non_negative"),
        CheckConstraint("valid_count >= 0", name="ck_jobs_valid_count_non_negative"),
        CheckConstraint("risky_count >= 0", name="ck_jobs_risky_count_non_negative"),
        CheckConstraint("invalid_count >= 0", name="ck_jobs_invalid_count_non_negative"),
        CheckConstraint(
            "status in ('queued', 'running', 'done', 'cancelled')",
            name="ck_jobs_status_allowed",
        ),
        CheckConstraint("processed <= total_emails", name="ck_jobs_processed_lte_total"),
        CheckConstraint(
            "valid_count + risky_count + invalid_count <= processed",
            name="ck_jobs_counts_lte_processed",
        ),
        Index("idx_jobs_user_id", "user_id"),
        Index("idx_jobs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    total_emails: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    processed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    valid_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    risky_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    invalid_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'queued'"),
    )
    r2_file_key: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="jobs")


class EmailCache(Base):
    __tablename__ = "email_cache"
    __table_args__ = (
        CheckConstraint(
            "status in ('valid', 'risky', 'invalid')",
            name="ck_email_cache_status_allowed",
        ),
        Index("idx_email_cache_expires_at", "expires_at"),
    )

    email: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        Computed("checked_at + interval '30 days'", persisted=True),
        nullable=False,
    )


class ProbeServer(Base):
    __tablename__ = "probe_servers"
    __table_args__ = (
        CheckConstraint(
            "probes_today >= 0",
            name="ck_probe_servers_probes_today_non_negative",
        ),
        CheckConstraint(
            "daily_limit > 0",
            name="ck_probe_servers_daily_limit_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    ip_address: Mapped[str] = mapped_column(INET, unique=True, nullable=False)
    probes_today: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    last_banned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    daily_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("200"),
    )
