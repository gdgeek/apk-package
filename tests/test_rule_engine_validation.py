"""RuleEngine.validate_rules() 单元测试"""

import base64

import pytest

from app.models.schemas import ImageRule, ScriptRule
from app.services.rule_engine import RuleEngine


@pytest.fixture
def engine():
    return RuleEngine()


# === target_path 验证 ===


class TestTargetPathValidation:
    def test_empty_target_path_script(self, engine):
        rule = ScriptRule(target_path="", pattern="foo", replacement="bar")
        result = engine.validate_rules([rule])
        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0].field == "target_path"
        assert result.errors[0].rule_index == 0

    def test_empty_target_path_image(self, engine):
        rule = ImageRule(target_path="", image_data=base64.b64encode(b"img").decode())
        result = engine.validate_rules([rule])
        assert not result.valid
        assert result.errors[0].field == "target_path"

    def test_whitespace_only_target_path(self, engine):
        rule = ScriptRule(target_path="   ", pattern="foo", replacement="bar")
        result = engine.validate_rules([rule])
        assert not result.valid
        assert result.errors[0].field == "target_path"

    def test_path_traversal_double_dot(self, engine):
        rule = ScriptRule(target_path="../etc/passwd", pattern="x", replacement="y")
        result = engine.validate_rules([rule])
        assert not result.valid
        assert any("'..' " in e.message or ".." in e.message for e in result.errors)

    def test_path_traversal_mid_path(self, engine):
        rule = ScriptRule(target_path="res/../smali/a.smali", pattern="x", replacement="y")
        result = engine.validate_rules([rule])
        assert not result.valid

    def test_absolute_path_rejected(self, engine):
        rule = ScriptRule(target_path="/etc/passwd", pattern="x", replacement="y")
        result = engine.validate_rules([rule])
        assert not result.valid
        assert any("'/'" in e.message or "相对路径" in e.message for e in result.errors)

    def test_valid_relative_path(self, engine):
        rule = ScriptRule(target_path="res/values/strings.xml", pattern="hello", replacement="world")
        result = engine.validate_rules([rule])
        assert result.valid
        assert len(result.errors) == 0


# === ScriptRule 验证 ===


class TestScriptRuleValidation:
    def test_empty_pattern(self, engine):
        rule = ScriptRule(target_path="a.smali", pattern="", replacement="bar")
        result = engine.validate_rules([rule])
        assert not result.valid
        assert result.errors[0].field == "pattern"

    def test_whitespace_only_pattern(self, engine):
        rule = ScriptRule(target_path="a.smali", pattern="   ", replacement="bar")
        result = engine.validate_rules([rule])
        assert not result.valid
        assert result.errors[0].field == "pattern"

    def test_valid_plain_pattern(self, engine):
        rule = ScriptRule(target_path="a.smali", pattern="hello", replacement="world")
        result = engine.validate_rules([rule])
        assert result.valid

    def test_valid_regex_pattern(self, engine):
        rule = ScriptRule(
            target_path="a.smali", pattern=r"\d+\.\d+", replacement="0.0", use_regex=True
        )
        result = engine.validate_rules([rule])
        assert result.valid

    def test_invalid_regex_pattern(self, engine):
        rule = ScriptRule(
            target_path="a.smali", pattern="[invalid(", replacement="x", use_regex=True
        )
        result = engine.validate_rules([rule])
        assert not result.valid
        assert result.errors[0].field == "pattern"
        assert "正则表达式" in result.errors[0].message

    def test_invalid_regex_not_checked_when_use_regex_false(self, engine):
        rule = ScriptRule(
            target_path="a.smali", pattern="[invalid(", replacement="x", use_regex=False
        )
        result = engine.validate_rules([rule])
        assert result.valid


# === ImageRule 验证 ===


class TestImageRuleValidation:
    def test_valid_base64(self, engine):
        data = base64.b64encode(b"fake image data").decode()
        rule = ImageRule(target_path="res/icon.png", image_data=data)
        result = engine.validate_rules([rule])
        assert result.valid

    def test_empty_image_data(self, engine):
        rule = ImageRule(target_path="res/icon.png", image_data="")
        result = engine.validate_rules([rule])
        assert not result.valid
        assert result.errors[0].field == "image_data"

    def test_invalid_base64(self, engine):
        rule = ImageRule(target_path="res/icon.png", image_data="not-valid-base64!!!")
        result = engine.validate_rules([rule])
        assert not result.valid
        assert result.errors[0].field == "image_data"
        assert "Base64" in result.errors[0].message


# === 批量验证 ===


class TestBatchValidation:
    def test_empty_rules_list(self, engine):
        result = engine.validate_rules([])
        assert result.valid
        assert len(result.errors) == 0

    def test_all_valid_rules(self, engine):
        rules = [
            ScriptRule(target_path="a.smali", pattern="x", replacement="y"),
            ImageRule(target_path="res/icon.png", image_data=base64.b64encode(b"img").decode()),
        ]
        result = engine.validate_rules(rules)
        assert result.valid
        assert len(result.errors) == 0

    def test_mixed_valid_and_invalid(self, engine):
        rules = [
            ScriptRule(target_path="a.smali", pattern="x", replacement="y"),  # valid
            ScriptRule(target_path="", pattern="x", replacement="y"),  # invalid: empty path
            ImageRule(target_path="res/icon.png", image_data="!!!"),  # invalid: bad base64
        ]
        result = engine.validate_rules(rules)
        assert not result.valid
        assert len(result.errors) == 2
        assert result.errors[0].rule_index == 1
        assert result.errors[1].rule_index == 2

    def test_multiple_errors_on_single_rule(self, engine):
        """A rule with both path traversal and absolute path should report both errors"""
        rule = ScriptRule(target_path="/../etc/passwd", pattern="x", replacement="y")
        result = engine.validate_rules([rule])
        assert not result.valid
        assert len(result.errors) >= 2  # both '..' and '/' errors

    def test_rule_index_tracking(self, engine):
        rules = [
            ScriptRule(target_path="ok.smali", pattern="x", replacement="y"),
            ScriptRule(target_path="ok.smali", pattern="x", replacement="y"),
            ScriptRule(target_path="", pattern="x", replacement="y"),  # invalid at index 2
        ]
        result = engine.validate_rules(rules)
        assert not result.valid
        assert all(e.rule_index == 2 for e in result.errors)
