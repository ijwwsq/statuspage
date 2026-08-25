"""Проверка чистой логики аптайма и общего статуса (без БД и сети)."""
from app.service import day_status, overall


def test_day_status():
    assert day_status(0, 0) == ("unknown", None)
    assert day_status(10, 10)[0] == "up"
    assert day_status(0, 10)[0] == "down"
    st, frac = day_status(9, 10)
    assert st == "partial" and 0 < frac < 1


def test_overall_operational():
    comps = [{"status": "operational"}, {"status": "unknown"}]
    assert overall(comps, False)["level"] == "operational"


def test_overall_active_incident_only():
    comps = [{"status": "operational"}]
    assert overall(comps, True)["level"] == "minor"


def test_overall_degraded_is_minor():
    assert overall([{"status": "degraded"}], False)["level"] == "minor"


def test_overall_major_wins():
    comps = [{"status": "operational"}, {"status": "major_outage"}]
    assert overall(comps, False)["level"] == "major"


def test_overall_maintenance():
    assert overall([{"status": "maintenance"}], False)["level"] == "maintenance"


def test_overall_empty():
    assert overall([], False)["level"] == "operational"
