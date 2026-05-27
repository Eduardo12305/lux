# tests/unit/test_scheduler.py
# Módulo: Testes de Cron/Scheduler + Triggers
# Status: IMPLEMENTADO

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from lux.agent.state import Channel
from lux.cron.jobs import CronJob, CronJobStore
from lux.cron.scheduler import CronScheduler
from lux.cron.triggers import (
    AutonomyLevel,
    ProactiveTrigger,
    ProactiveTriggerEngine,
)


# ── CronJob ───────────────────────────────────────────────────────────────


def test_cron_job_defaults():
    job = CronJob(name="test", prompt="resumir emails", schedule="0 9 * * 1-5")
    assert job.id
    assert job.is_active is True
    assert job.run_count == 0
    assert job.skills == []


def test_cron_job_to_dict():
    job = CronJob(
        id="j1", user_id="u1", name="daily",
        prompt="resumo", schedule="0 9 * * *",
        skills=["email-triage"], toolsets=["email"],
        delivery_channel=Channel.CLI,
    )
    d = job.to_dict()
    assert d["id"] == "j1"
    assert d["skills"] == ["email-triage"]
    assert d["delivery_channel"] == "cli"


def test_cron_job_from_dict():
    data = {
        "id": "j2", "user_id": "u1", "name": "test",
        "prompt": "hello", "schedule": "0 * * * *",
        "skills": [], "toolsets": ["web"],
        "delivery_channel": "telegram", "delivery_target": "123",
        "is_active": False, "run_count": 5,
        "last_run": None, "next_run": None,
        "created_at": "2026-05-20T10:00:00+00:00",
    }
    job = CronJob.from_dict(data)
    assert job.name == "test"
    assert job.toolsets == ["web"]
    assert job.is_active is False
    assert job.run_count == 5
    assert job.delivery_channel == Channel.TELEGRAM


# ── CronJobStore ──────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    return CronJobStore(path=tmp_path / "jobs.json")


def test_store_create(store):
    job = CronJob(name="daily", prompt="test", schedule="0 9 * * *")
    created = store.create(job)
    assert created.id == job.id
    assert store.get(job.id) is not None


def test_store_list_all(store):
    store.create(CronJob(name="j1", prompt="a", schedule="* * * * *"))
    store.create(CronJob(name="j2", prompt="b", schedule="* * * * *"))
    jobs = store.list_all()
    assert len(jobs) == 2


def test_store_list_by_user(store):
    store.create(CronJob(user_id="u1", name="j1", prompt="a", schedule="* * * * *"))
    store.create(CronJob(user_id="u2", name="j2", prompt="b", schedule="* * * * *"))
    assert len(store.list_all("u1")) == 1
    assert len(store.list_all("u2")) == 1


def test_store_list_active(store):
    store.create(CronJob(name="active", prompt="a", schedule="* * * * *", is_active=True))
    j = CronJob(name="inactive", prompt="b", schedule="* * * * *", is_active=False)
    store.create(j)
    assert len(store.list_active()) == 1


def test_store_update(store):
    job = store.create(CronJob(name="old", prompt="x", schedule="* * * * *"))
    job.name = "new"
    assert store.update(job) is True
    assert store.get(job.id).name == "new"


def test_store_update_nonexistent(store):
    job = CronJob(id="ghost", name="x", prompt="y", schedule="* * * * *")
    assert store.update(job) is False


def test_store_delete(store):
    job = store.create(CronJob(name="del", prompt="x", schedule="* * * * *"))
    assert store.delete(job.id) is True
    assert store.get(job.id) is None


def test_store_delete_nonexistent(store):
    assert store.delete("ghost") is False


def test_store_get_due(store):
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)

    store.create(CronJob(name="due", prompt="a", schedule="* * * * *",
                          next_run=past, is_active=True))
    store.create(CronJob(name="future", prompt="b", schedule="* * * * *",
                          next_run=future, is_active=True))
    store.create(CronJob(name="inactive_due", prompt="c", schedule="* * * * *",
                          next_run=past, is_active=False))

    due = store.get_due(now)
    assert len(due) == 1
    assert due[0].name == "due"


# ── CronScheduler ─────────────────────────────────────────────────────────


@pytest.fixture
def scheduler(tmp_path):
    store = CronJobStore(path=tmp_path / "jobs.json")
    return CronScheduler(store=store)


def test_scheduler_create_job(scheduler):
    job = scheduler.create_job(
        user_id="u1", name="test", prompt="hello",
        schedule="0 9 * * *", toolsets=["web"],
    )
    assert job.id
    assert job.next_run is not None


def test_scheduler_list_jobs(scheduler):
    scheduler.create_job("u1", "j1", "a", "* * * * *")
    scheduler.create_job("u1", "j2", "b", "* * * * *")
    assert len(scheduler.list_jobs()) == 2


def test_scheduler_delete_job(scheduler):
    job = scheduler.create_job("u1", "del", "x", "* * * * *")
    assert scheduler.delete_job(job.id) is True
    assert scheduler.delete_job("ghost") is False


def test_scheduler_toggle_job(scheduler):
    job = scheduler.create_job("u1", "toggle", "x", "* * * * *")
    toggled = scheduler.toggle_job(job.id)
    assert toggled is not None
    assert toggled.is_active is False
    toggled2 = scheduler.toggle_job(job.id)
    assert toggled2.is_active is True


def test_scheduler_toggle_nonexistent(scheduler):
    assert scheduler.toggle_job("ghost") is None


# ── ProactiveTrigger ─────────────────────────────────────────────────────


def test_trigger_cooled_down_no_last_fire():
    t = ProactiveTrigger(id="test", condition="x", action="y")
    assert t.is_cooled_down() is True


def test_trigger_cooled_down_recent():
    t = ProactiveTrigger(id="test", condition="x", action="y",
                          cooldown_minutes=30)
    t.last_fired = datetime.now(timezone.utc)
    assert t.is_cooled_down() is False


def test_trigger_fire():
    t = ProactiveTrigger(id="test", condition="x", action="y")
    t.fire()
    assert t.last_fired is not None
    assert t.is_cooled_down() is False


# ── ProactiveTriggerEngine ────────────────────────────────────────────────


@pytest.fixture
def trigger_engine():
    return ProactiveTriggerEngine()


def test_engine_has_builtin_triggers(trigger_engine):
    triggers = trigger_engine.list_triggers()
    assert len(triggers) >= 4
    ids = {t.id for t in triggers}
    assert "vram_high" in ids
    assert "disk_low" in ids


def test_engine_add_custom_trigger(trigger_engine):
    t = ProactiveTrigger(id="custom", condition="test", action="do")
    trigger_engine.add_trigger(t)
    assert len(trigger_engine.list_triggers()) > 4


def test_engine_remove_trigger(trigger_engine):
    t = ProactiveTrigger(id="custom", condition="test", action="do")
    trigger_engine.add_trigger(t)
    trigger_engine.remove_trigger("custom")
    ids = {t.id for t in trigger_engine.list_triggers()}
    assert "custom" not in ids
