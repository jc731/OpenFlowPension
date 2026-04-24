import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PlanTier(TimestampMixin, Base):
    __tablename__ = "plan_tiers"

    tier_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    tier_label: Mapped[str] = mapped_column(String, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan_configurations: Mapped[list["PlanConfiguration"]] = relationship(back_populates="plan_tier")


class PlanType(TimestampMixin, Base):
    __tablename__ = "plan_types"

    plan_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    plan_label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan_configurations: Mapped[list["PlanConfiguration"]] = relationship(back_populates="plan_type")


class PlanConfiguration(TimestampMixin, Base):
    __tablename__ = "plan_configurations"
    __table_args__ = (
        UniqueConstraint("plan_tier_id", "plan_type_id", "employment_type", "effective_date"),
    )

    plan_tier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_tiers.id"), nullable=False)
    plan_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_types.id"), nullable=False)
    employment_type: Mapped[str] = mapped_column(String, nullable=False)

    benefit_multiplier: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    fac_years: Mapped[int] = mapped_column(Integer, nullable=False)
    vesting_years: Mapped[int] = mapped_column(Integer, nullable=False)
    normal_retirement_age: Mapped[int] = mapped_column(Integer, nullable=False)
    early_retirement_age: Mapped[int | None] = mapped_column(Integer, nullable=True)

    member_contribution_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    employer_contribution_rate: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)

    cola_rate: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    cola_cap: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    cola_type: Mapped[str | None] = mapped_column(String, nullable=True)

    sick_time_eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sick_time_conversion_rate: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)

    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    superseded_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    plan_tier: Mapped["PlanTier"] = relationship(back_populates="plan_configurations")
    plan_type: Mapped["PlanType"] = relationship(back_populates="plan_configurations")


class SystemConfiguration(Base):
    __tablename__ = "system_configurations"
    __table_args__ = (
        UniqueConstraint("config_key", "effective_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )

    config_key: Mapped[str] = mapped_column(String, nullable=False)
    config_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    superseded_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    set_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
