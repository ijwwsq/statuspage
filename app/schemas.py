"""Pydantic-схемы запросов admin-API."""
from datetime import datetime

from pydantic import BaseModel, Field

INCIDENT_STATUSES = {"investigating", "identified", "monitoring", "resolved"}
IMPACTS = {"none", "minor", "major", "critical"}
COMPONENT_STATUSES = {
    "operational", "degraded", "partial_outage", "major_outage", "maintenance",
}


class Login(BaseModel):
    token: str


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    type: str = "incident"  # incident | maintenance
    impact: str = "minor"
    status: str = "investigating"
    component_keys: list[str] = []
    scheduled_for: datetime | None = None
    scheduled_until: datetime | None = None


class IncidentUpdateCreate(BaseModel):
    body: str = Field(min_length=1)
    status: str


class ComponentStatus(BaseModel):
    status: str | None = None  # null → снять ручной override, вернуться к монитору
