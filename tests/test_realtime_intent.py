from __future__ import annotations

from clogem.services.realtime_intent import (
    local_datetime_context_block,
    needs_realtime_web_assist,
)


def test_needs_realtime_detects_weather_in_city() -> None:
    assert needs_realtime_web_assist("what's the weather today in Osnabrück") is True


def test_needs_realtime_detects_forecast() -> None:
    assert needs_realtime_web_assist("forecast for Berlin tomorrow?") is True


def test_needs_realtime_detects_headlines() -> None:
    assert needs_realtime_web_assist("latest news headlines today") is True


def test_needs_realtime_false_for_code() -> None:
    assert needs_realtime_web_assist("def fetch_weather():\n    pass") is False


def test_needs_realtime_false_for_weather_app_build() -> None:
    assert needs_realtime_web_assist("build a weather api component") is False


def test_local_datetime_context_non_empty() -> None:
    assert "Local date/time" in local_datetime_context_block()
    assert "Local timezone" in local_datetime_context_block()
