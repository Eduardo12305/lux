# tests/unit/test_reflection.py
# Módulo: Testes de Reflection Engine
# Status: IMPLEMENTADO

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone

from lux.reflection.post_task import PostTaskReflector, ReflectionResult
from lux.reflection.skill_evolver import SkillEvolver, EvolutionResult, SkillUsage
from lux.reflection.behavior_analyzer import UserBehaviorAnalyzer, BehaviorReport
from lux.reflection.dspy_optimizer import DSPyOptimizer


# ── PostTaskReflector ─────────────────────────────────────────────────────


def test_reflection_result_defaults():
    r = ReflectionResult(task_id="t1", session_id="s1", user_id="u1", outcome="SUCCESS")
    assert r.what_worked == []
    assert r.what_failed == []
    assert r.root_cause is None
    assert r.memory_content is None


def test_reflection_result_with_insights():
    r = ReflectionResult(
        task_id="t1", session_id="s1", user_id="u1", outcome="PARTIAL",
        what_worked=["rapido", "preciso"],
        what_failed=["timeout no deploy"],
        root_cause="conexao SSH instavel",
        lessons=["verificar conectividade antes do deploy"],
        memory_content="deploy precisa de SSH estavel",
    )
    assert len(r.what_worked) == 2
    assert "timeout" in r.what_failed[0]
    assert r.root_cause is not None


def test_reflector_parse_json_valid():
    reflector = PostTaskReflector()
    raw = '{"what_worked":["a"],"what_failed":[],"root_cause":null,"lessons":[],"skill_opportunity":{"exists":false},"memory_worthy":{"exists":false},"user_insight":{"exists":false}}'
    data = reflector._parse_json(raw)
    assert data["what_worked"] == ["a"]


def test_reflector_parse_json_with_text():
    reflector = PostTaskReflector()
    raw = 'algum texto antes {"what_worked":["x"],"what_failed":[],"root_cause":null,"lessons":[],"skill_opportunity":{"exists":false},"memory_worthy":{"exists":false},"user_insight":{"exists":false}} texto depois'
    data = reflector._parse_json(raw)
    assert data["what_worked"] == ["x"]


def test_reflector_parse_json_invalid():
    reflector = PostTaskReflector()
    data = reflector._parse_json("texto sem json valido aqui")
    assert data == {}


def test_reflector_parse_json_empty():
    reflector = PostTaskReflector()
    data = reflector._parse_json("")
    assert data == {}


@pytest.mark.asyncio
async def test_reflector_without_llm(tmp_path):
    from lux.memory.session_db import SessionDB
    db = SessionDB(db_path=tmp_path / "ref_test.db")
    reflector = PostTaskReflector(llama=None, session_db=db)

    result = await reflector.reflect(
        task_id="t1", session_id="s1", user_id="u1",
        task_description="teste simples",
        iterations_used=3, max_iterations=50,
        tools_used=["file_read"], errors=[],
        outcome="SUCCESS",
    )
    assert result.task_id == "t1"
    assert result.outcome == "SUCCESS"


@pytest.mark.asyncio
async def test_reflector_saves_to_db(tmp_path):
    from lux.memory.session_db import SessionDB
    db = SessionDB(db_path=tmp_path / "ref_persist.db")
    reflector = PostTaskReflector(llama=None, session_db=db)

    result = ReflectionResult(
        task_id="t2", session_id="s2", user_id="u1", outcome="SUCCESS",
        what_worked=["ok"], what_failed=[], lessons=["l1"],
        memory_content="salvar isso",
    )
    await reflector._persist_reflection(result)

    conn = await db._get_conn()
    cursor = await conn.execute("SELECT COUNT(*) FROM task_reflections")
    count = (await cursor.fetchone())[0]
    assert count == 1


@pytest.mark.asyncio
async def test_reflector_queues_skill(tmp_path):
    from lux.memory.session_db import SessionDB
    db = SessionDB(db_path=tmp_path / "ref_queue.db")
    reflector = PostTaskReflector(llama=None, session_db=db)

    result = ReflectionResult(
        task_id="t3", session_id="s3", user_id="u1", outcome="SUCCESS",
        skill_opp_name="nova-skill", skill_opp_reason="util",
    )
    await reflector._queue_skill(result)

    conn = await db._get_conn()
    cursor = await conn.execute("SELECT COUNT(*) FROM skill_queue")
    count = (await cursor.fetchone())[0]
    assert count == 1


# ── SkillEvolver ──────────────────────────────────────────────────────────


def test_skill_usage_creation():
    u = SkillUsage(skill_name="test", task_id="t1", success=True, iterations_used=5)
    assert u.skill_name == "test"
    assert u.success is True


@pytest.mark.asyncio
async def test_evolver_not_enough_uses():
    evolver = SkillEvolver()
    evolver.record_usage("s1", "t1", True, 3)
    result = await evolver.check_and_evolve("s1")
    assert result.evolved is False
    assert "Poucos usos" in result.reason


@pytest.mark.asyncio
async def test_evolver_quality_ok():
    evolver = SkillEvolver()
    for i in range(5):
        evolver.record_usage("s2", f"t{i}", True, 2)
    result = await evolver.check_and_evolve("s2")
    assert result.evolved is False
    assert "Qualidade suficiente" in result.reason


@pytest.mark.asyncio
async def test_evolver_detects_failures():
    evolver = SkillEvolver()
    for i in range(3):
        evolver.record_usage("s3", f"t{i}", True, 2)
    evolver.record_usage("s3", "t3", False, 8, ["erro critico"])
    evolver.record_usage("s3", "t4", False, 10, ["erro critico"])
    result = await evolver.check_and_evolve("s3")
    assert result.evolved is True
    assert "recorrentes" in result.reason


@pytest.mark.asyncio
async def test_evolver_identify_patterns():
    evolver = SkillEvolver()
    trajectories = [
        {"tools_used": ["a", "b", "c"]},
        {"tools_used": ["a", "b", "c"]},
        {"tools_used": ["x", "y"]},
    ]
    patterns = await evolver.identify_patterns(trajectories)
    assert len(patterns) >= 1


# ── UserBehaviorAnalyzer ─────────────────────────────────────────────────


def test_behavior_report_defaults():
    r = BehaviorReport(user_id="u1")
    assert r.insights == []
    assert r.top_tools == []


@pytest.mark.asyncio
async def test_behavior_analyzer_should_analyze(tmp_path):
    from lux.memory.session_db import SessionDB
    db = SessionDB(db_path=tmp_path / "beh_test.db")
    analyzer = UserBehaviorAnalyzer(session_db=db)
    result = await analyzer.should_analyze("u1")
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_behavior_analyzer_no_data(tmp_path):
    from lux.memory.session_db import SessionDB
    db = SessionDB(db_path=tmp_path / "beh_empty.db")
    analyzer = UserBehaviorAnalyzer(session_db=db)
    report = await analyzer.analyze("u1")
    assert report.user_id == "u1"


# ── DSPyOptimizer ─────────────────────────────────────────────────────────


def test_dspy_optimizer_session_count():
    opt = DSPyOptimizer()
    assert opt._session_count == 0
    opt.track_session()
    assert opt._session_count == 1


@pytest.mark.asyncio
async def test_dspy_should_not_optimize_early():
    opt = DSPyOptimizer()
    opt.track_session()
    assert await opt.should_optimize() is False


@pytest.mark.asyncio
async def test_dspy_should_optimize_at_n():
    opt = DSPyOptimizer()
    opt._session_count = 25
    assert await opt.should_optimize() is True


@pytest.mark.asyncio
async def test_dspy_no_examples_returns_none():
    opt = DSPyOptimizer()
    opt._session_count = 25
    result = await opt.maybe_optimize()
    assert result is None
