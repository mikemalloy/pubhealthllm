"""Tests for ARCHITECTURE.md §3a contract types: ArtifactType, Artifact, Meta, AskResponse, Plan."""
import pytest
from enum import Enum

from pubhealth_llm.app.schemas import (
    ArtifactType,
    Artifact,
    AskResponse,
    Meta,
    Plan,
)


# ---------------------------------------------------------------------------
# ArtifactType
# ---------------------------------------------------------------------------


def test_artifact_type_is_str_enum():
    assert issubclass(ArtifactType, str)
    assert issubclass(ArtifactType, Enum)


def test_artifact_type_members():
    members = {m.value for m in ArtifactType}
    assert members == {
        "report", "table", "comparison", "ranking",
        "choropleth_map", "mortality", "decision_tree",
    }


def test_artifact_type_values_are_strings():
    for member in ArtifactType:
        assert isinstance(member.value, str)


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


def test_artifact_valid():
    a = Artifact(type=ArtifactType.report, title="Diabetes Brief", payload={"key": "value"})
    assert a.type == ArtifactType.report
    assert a.title == "Diabetes Brief"
    assert a.payload == {"key": "value"}


def test_artifact_rejects_invalid_type():
    with pytest.raises(Exception):
        Artifact(type="invalid_type", title="t", payload={})


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


def test_meta_defaults():
    m = Meta(intent="data query")
    assert m.tools_used == []
    assert m.model == ""
    assert m.timing_ms == 0


def test_meta_explicit_values():
    m = Meta(
        intent="county comparison",
        tools_used=["tool_compare_locations"],
        model="claude-sonnet-4-6",
        timing_ms=1500,
    )
    assert m.tools_used == ["tool_compare_locations"]
    assert m.model == "claude-sonnet-4-6"
    assert m.timing_ms == 1500


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def test_plan_chat_mode():
    p = Plan(mode="chat", intent="what can you do", reason="no data keywords")
    assert p.mode == "chat"
    assert p.artifact_type is None


def test_plan_artifact_mode_with_type():
    p = Plan(
        mode="artifact",
        artifact_type=ArtifactType.report,
        intent="diabetes in Travis County",
        reason="named county + disease keyword",
    )
    assert p.mode == "artifact"
    assert p.artifact_type == ArtifactType.report


def test_plan_has_reason_field():
    p = Plan(mode="chat", intent="greeting", reason="no data needed")
    assert p.reason == "no data needed"


def test_plan_artifact_type_defaults_to_none():
    p = Plan(mode="chat", intent="hi", reason="greeting")
    assert p.artifact_type is None


def test_plan_chat_mode_rejects_artifact_type():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Plan(
            mode="chat",
            artifact_type=ArtifactType.report,
            intent="x",
            reason="should fail",
        )


# ---------------------------------------------------------------------------
# AskResponse — model validator
# ---------------------------------------------------------------------------


def test_ask_response_artifact_mode_requires_artifact():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AskResponse(
            mode="artifact",
            chat_message="teaser",
            artifact=None,
            meta=Meta(intent="x"),
        )


def test_ask_response_chat_mode_rejects_artifact():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AskResponse(
            mode="chat",
            chat_message="hi",
            artifact=Artifact(type=ArtifactType.report, title="t", payload={}),
            meta=Meta(intent="x"),
        )


def test_ask_response_chat_mode_valid():
    r = AskResponse(
        mode="chat",
        chat_message="Here is some info.",
        artifact=None,
        meta=Meta(intent="capability question"),
    )
    assert r.mode == "chat"
    assert r.artifact is None


def test_ask_response_artifact_mode_valid():
    r = AskResponse(
        mode="artifact",
        chat_message="Diabetes rates are elevated.",
        artifact=Artifact(
            type=ArtifactType.report,
            title="Diabetes in Travis County",
            payload={"summary": "..."},
        ),
        meta=Meta(intent="diabetes statistics"),
    )
    assert r.mode == "artifact"
    assert r.artifact.type == ArtifactType.report
