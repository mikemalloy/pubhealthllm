# backend/tests/test_schemas_multi_agent.py
"""Tests for multi-agent schemas: Plan, ArtifactEnvelope, AskMeta, AskResponse."""
import pytest

from pubhealth_llm.app.schemas import ArtifactEnvelope, AskMeta, AskResponse, Plan


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def test_plan_artifact_type_is_optional():
    """artifact_type is optional — can be None even in artifact mode."""
    p = Plan(
        intent="look up diabetes statistics",
        mode="artifact",
        artifact_type=None,
        dispatch_target="reporter",
        confidence=0.95,
    )
    assert p.mode == "artifact"
    assert p.dispatch_target == "reporter"
    assert p.artifact_type is None


def test_plan_chat_mode_valid():
    p = Plan(
        intent="clarifying question about the tool",
        mode="chat",
        artifact_type=None,
        dispatch_target="responder",
        confidence=0.8,
    )
    assert p.mode == "chat"
    assert p.dispatch_target == "responder"


def test_plan_confidence_rejects_above_one():
    with pytest.raises(Exception):
        Plan(
            intent="x",
            mode="chat",
            dispatch_target="responder",
            confidence=1.5,
        )


def test_plan_confidence_rejects_below_zero():
    with pytest.raises(Exception):
        Plan(
            intent="x",
            mode="chat",
            dispatch_target="responder",
            confidence=-0.1,
        )


def test_plan_mode_dispatch_target_must_be_compatible():
    """mode='chat' with dispatch_target='reporter' must raise ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Plan(
            intent="x",
            mode="chat",
            dispatch_target="reporter",
            confidence=0.5,
        )


# ---------------------------------------------------------------------------
# AskResponse
# ---------------------------------------------------------------------------


def test_ask_response_chat_mode_has_no_artifact():
    r = AskResponse(
        mode="chat",
        chat_message="I can look up public health statistics.",
        artifact=None,
        meta=AskMeta(
            intent="capability question",
            tools_used=[],
            model="claude-haiku-4-5-20251001",
            timing_ms=42,
        ),
    )
    assert r.mode == "chat"
    assert r.artifact is None
    assert r.chat_message == "I can look up public health statistics."


def test_ask_response_artifact_mode_has_envelope():
    r = AskResponse(
        mode="artifact",
        chat_message="Here is your diabetes report.",
        artifact=ArtifactEnvelope(
            type="report",
            title="Diabetes in Travis County, TX",
            payload={"summary": "Rates are elevated."},
        ),
        meta=AskMeta(
            intent="diabetes statistics",
            tools_used=["tool_get_health_statistics"],
            model="claude-sonnet-4-6",
            timing_ms=1800,
        ),
    )
    assert r.artifact is not None
    assert r.artifact.type == "report"
    assert r.artifact.payload["summary"] == "Rates are elevated."
    assert r.meta.timing_ms == 1800


def test_ask_response_chat_message_always_present():
    """chat_message must be a non-empty string in both modes."""
    r = AskResponse(
        mode="artifact",
        chat_message="Brief teaser text.",
        artifact=ArtifactEnvelope(type="report", title="t", payload={}),
        meta=AskMeta(intent="x", tools_used=[], model="m", timing_ms=0),
    )
    assert isinstance(r.chat_message, str)
    assert len(r.chat_message) > 0


def test_ask_response_artifact_mode_rejects_missing_artifact():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AskResponse(
            mode="artifact",
            chat_message="Teaser",
            artifact=None,
            meta=AskMeta(intent="x", tools_used=[], model="m", timing_ms=0),
        )


def test_ask_response_chat_mode_rejects_artifact_present():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AskResponse(
            mode="chat",
            chat_message="Response",
            artifact=ArtifactEnvelope(type="report", title="t", payload={}),
            meta=AskMeta(intent="x", tools_used=[], model="m", timing_ms=0),
        )
