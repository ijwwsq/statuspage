"""ORM-модели statuspage. Все таблицы с префиксом status_ — не конфликтуют при переносе."""
import datetime as dt

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Component(Base):
    __tablename__ = "status_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    group: Mapped[str] = mapped_column(String(120), default="Services")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    method: Mapped[str] = mapped_column(String(10), default="GET")
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # статус из монитора; manual_status (если задан админом) его перекрывает
    monitored_status: Mapped[str] = mapped_column(String(30), default="unknown")
    manual_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )

    @property
    def status(self) -> str:
        return self.manual_status or self.monitored_status


class Check(Base):
    __tablename__ = "status_checks"
    # составной индекс покрывает агрегации "по компоненту за период"; отдельный ts — для прунинга
    __table_args__ = (Index("ix_status_checks_comp_ts", "component_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    component_id: Mapped[int] = mapped_column(
        ForeignKey("status_components.id", ondelete="CASCADE")
    )
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    ok: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)


class Incident(Base):
    __tablename__ = "status_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(20), default="incident")  # incident | maintenance
    status: Mapped[str] = mapped_column(String(20), default="investigating")
    impact: Mapped[str] = mapped_column(String(20), default="minor")
    auto: Mapped[bool] = mapped_column(Boolean, default=False)  # заведён монитором
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_for: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_until: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    updates: Mapped[list["IncidentUpdate"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentUpdate.created_at",
    )
    components: Mapped[list["IncidentComponent"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class IncidentUpdate(Base):
    __tablename__ = "status_incident_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("status_incidents.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)

    incident: Mapped[Incident] = relationship(back_populates="updates")


class IncidentComponent(Base):
    __tablename__ = "status_incident_components"

    incident_id: Mapped[int] = mapped_column(
        ForeignKey("status_incidents.id", ondelete="CASCADE"), primary_key=True
    )
    component_id: Mapped[int] = mapped_column(
        ForeignKey("status_components.id", ondelete="CASCADE"), primary_key=True
    )

    incident: Mapped[Incident] = relationship(back_populates="components")
    component: Mapped[Component] = relationship()


class Subscriber(Base):
    __tablename__ = "status_subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), default="telegram")
    target: Mapped[str] = mapped_column(String(120), index=True)  # telegram chat_id
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
