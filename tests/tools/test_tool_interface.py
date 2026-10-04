"""tests/tools/test_tool_interface.py"""
from __future__ import annotations

from .conftest import EchoTool

from core.tools.metadata import Capability, RiskLevel, ToolCategory, ToolMetadata
from core.tools.results import ToolResult
from core.tools.schemas import ParamSchema, ToolSchema


def test_tool_has_name_description_metadata():
    tool = EchoTool()
    assert tool.name == "echo_tool"
    assert tool.description
    assert tool.metadata.risk_level == RiskLevel.LOW
    assert tool.metadata.category == ToolCategory.SYSTEM


def test_tool_metadata_risk_levels_exist():
    assert set(RiskLevel) == {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL}


def test_tool_result_ok():
    result = ToolResult.ok("t", data="hello")
    assert result.success is True
    assert result.data == "hello"
    assert result.message == "hello"


def test_tool_result_fail():
    result = ToolResult.fail("t", error="bad thing", error_type="ValueError")
    assert result.success is False
    assert result.error == "bad thing"
    assert "bad thing" in result.message


def test_tool_result_as_model_text():
    result = ToolResult.ok("t", data="hi", message="custom message")
    assert result.as_model_text() == "custom message"


def test_schema_required_names():
    schema = ToolSchema((
        ParamSchema("a", "string", required=True),
        ParamSchema("b", "string", required=False),
    ))
    assert schema.required_names() == ["a"]


def test_schema_validate_missing_required():
    schema = ToolSchema((ParamSchema("a", "string", required=True),))
    errors = schema.validate({})
    assert len(errors) == 1
    assert "a" in errors[0]


def test_schema_validate_wrong_type():
    schema = ToolSchema((ParamSchema("count", "integer"),))
    errors = schema.validate({"count": "not a number"})
    assert len(errors) == 1


def test_schema_validate_enum():
    schema = ToolSchema((ParamSchema("mode", "string", enum=("a", "b")),))
    assert schema.validate({"mode": "a"}) == []
    assert len(schema.validate({"mode": "z"})) == 1


def test_schema_validate_tolerates_extra_args():
    schema = ToolSchema((ParamSchema("a", "string", required=True),))
    errors = schema.validate({"a": "x", "unexpected_extra": "y"})
    assert errors == []


def test_gemini_declaration_shape():
    tool = EchoTool()
    decl = tool.gemini_declaration()
    assert decl["name"] == "echo_tool"
    assert decl["parameters"]["type"] == "OBJECT"
    assert "message" in decl["parameters"]["properties"]
    assert decl["parameters"]["properties"]["message"]["type"] == "STRING"
    assert decl["parameters"]["properties"]["count"]["type"] == "INTEGER"
    assert decl["parameters"]["properties"]["shout"]["type"] == "BOOLEAN"
    assert decl["parameters"]["required"] == ["message"]
