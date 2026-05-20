# tests/unit/test_vram_guard.py
# Módulo: Testes de VRAMGuard
# Status: IMPLEMENTADO

from __future__ import annotations

import pytest

from lux.models.vram_guard import VRAMGuard


@pytest.fixture
def vram_guard():
    return VRAMGuard(budget_gb=16.0)


def test_vram_guard_default_thresholds(vram_guard):
    assert vram_guard.budget_gb == 16.0
    assert vram_guard.thresholds["nominal"] == 12.0
    assert vram_guard.thresholds["warning"] == 13.12
    assert vram_guard.thresholds["critical"] == 14.08
    assert vram_guard.thresholds["oom"] == 15.04


def test_vram_guard_model_vram(vram_guard):
    assert vram_guard.model_vram["qwen3-14b-q4"] == 9.5
    assert vram_guard.model_vram["qwen3-1.7b-q4"] == 1.2
    assert vram_guard.model_vram["whisper-small"] == 0.5


@pytest.mark.asyncio
async def test_can_load_model_yes(vram_guard):
    vram_guard._cached_usage = 5.0
    vram_guard._last_check = 0

    async def fake_get_usage():
        return 5.0

    vram_guard.get_usage = fake_get_usage
    result = await vram_guard.can_load_model("whisper-small")
    assert result is True


@pytest.mark.asyncio
async def test_can_load_model_no(vram_guard):
    vram_guard._cached_usage = 14.0
    vram_guard._last_check = 0

    async def fake_get_usage():
        return 14.0

    vram_guard.get_usage = fake_get_usage
    result = await vram_guard.can_load_model("whisper-small")
    assert result is False


@pytest.mark.asyncio
async def test_usage_ratio(vram_guard):
    async def fake_get_usage():
        return 8.0

    vram_guard.get_usage = fake_get_usage
    ratio = await vram_guard.usage_ratio()
    assert ratio == 0.5


@pytest.mark.asyncio
async def test_get_threshold_status_nominal(vram_guard):
    async def fake_get_usage():
        return 8.0

    vram_guard.get_usage = fake_get_usage
    status = await vram_guard.get_threshold_status()
    assert status == "nominal"


@pytest.mark.asyncio
async def test_get_threshold_status_warning(vram_guard):
    async def fake_get_usage():
        return 13.5

    vram_guard.get_usage = fake_get_usage
    status = await vram_guard.get_threshold_status()
    assert status == "warning"


@pytest.mark.asyncio
async def test_get_threshold_status_critical(vram_guard):
    async def fake_get_usage():
        return 14.5

    vram_guard.get_usage = fake_get_usage
    status = await vram_guard.get_threshold_status()
    assert status == "critical"


@pytest.mark.asyncio
async def test_get_threshold_status_oom(vram_guard):
    async def fake_get_usage():
        return 15.5

    vram_guard.get_usage = fake_get_usage
    status = await vram_guard.get_threshold_status()
    assert status == "oom"


@pytest.mark.asyncio
async def test_can_load_model_with_custom_vram(vram_guard):
    async def fake_get_usage():
        return 10.0

    vram_guard.get_usage = fake_get_usage
    result = await vram_guard.can_load_model("any-model", vram_gb=3.0)
    assert result is True
    result2 = await vram_guard.can_load_model("big-model", vram_gb=6.0)
    assert result2 is False
