"""Кэш публичной сводки: короткий TTL + ручная инвалидация при мутациях."""
import time

_TTL = 5.0
_state: dict = {"ts": 0.0, "data": None}


def get(builder):
    """Вернуть сводку из кэша или пересчитать через builder()."""
    now = time.monotonic()
    if _state["data"] is None or now - _state["ts"] > _TTL:
        _state["data"] = builder()
        _state["ts"] = now
    return _state["data"]


def invalidate() -> None:
    _state["data"] = None
