"""Unit tests for _extract_tools_used in agent.py."""
from dataclasses import dataclass, field
from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart


def _make_fake_result(tool_names: list[str], output_tool_name: str = "final_result"):
    """Build a fake AgentRunResult-like object for testing _extract_tools_used."""
    # We just need an object with new_messages() and _output_tool_name
    parts = [
        ToolCallPart(tool_name=name, args={})
        for name in tool_names
    ]
    response = ModelResponse(parts=parts)

    @dataclass
    class FakeResult:
        _output_tool_name: str
        _messages: list

        def new_messages(self):
            return self._messages

    return FakeResult(
        _output_tool_name=output_tool_name,
        _messages=[response],
    )


def test_extract_tools_used_excludes_output_tool():
    from pubhealth_llm.app.agent import _extract_tools_used
    fake = _make_fake_result(
        ["tool_get_health_statistics", "final_result", "tool_search_mmwr_reports"],
        output_tool_name="final_result",
    )
    result = _extract_tools_used(fake)
    assert result == ["tool_get_health_statistics", "tool_search_mmwr_reports"]


def test_extract_tools_used_deduplicates_preserving_order():
    from pubhealth_llm.app.agent import _extract_tools_used
    fake = _make_fake_result(
        ["tool_get_health_statistics", "tool_get_health_statistics", "tool_search_mmwr_reports"],
    )
    result = _extract_tools_used(fake)
    assert result == ["tool_get_health_statistics", "tool_search_mmwr_reports"]


def test_extract_tools_used_empty_when_no_tool_calls():
    from pubhealth_llm.app.agent import _extract_tools_used
    # Message with no ToolCallParts
    @dataclass
    class FakeResult:
        _output_tool_name: str = "final_result"

        def new_messages(self):
            return [ModelResponse(parts=[TextPart(content="hi")])]

    result = _extract_tools_used(FakeResult())
    assert result == []
