"""RuleEngine.apply_script_rule() 单元测试"""

import pytest

from app.models.schemas import ScriptRule
from app.services.rule_engine import RuleEngine


@pytest.fixture
def engine():
    return RuleEngine()


class TestApplyScriptRulePlainText:
    """普通文本匹配替换"""

    def test_simple_replacement(self, engine, tmp_path):
        target = tmp_path / "test.smali"
        target.write_text("hello world", encoding="utf-8")

        rule = ScriptRule(
            target_path="test.smali", pattern="hello", replacement="goodbye"
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_text(encoding="utf-8") == "goodbye world"

    def test_multiple_occurrences(self, engine, tmp_path):
        target = tmp_path / "test.txt"
        target.write_text("aaa bbb aaa", encoding="utf-8")

        rule = ScriptRule(
            target_path="test.txt", pattern="aaa", replacement="ccc"
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_text(encoding="utf-8") == "ccc bbb ccc"

    def test_no_match_leaves_file_unchanged(self, engine, tmp_path):
        original = "nothing to replace here"
        target = tmp_path / "test.txt"
        target.write_text(original, encoding="utf-8")

        rule = ScriptRule(
            target_path="test.txt", pattern="missing", replacement="found"
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_text(encoding="utf-8") == original

    def test_nested_path(self, engine, tmp_path):
        subdir = tmp_path / "res" / "values"
        subdir.mkdir(parents=True)
        target = subdir / "strings.xml"
        target.write_text('<string name="app">OldName</string>', encoding="utf-8")

        rule = ScriptRule(
            target_path="res/values/strings.xml",
            pattern="OldName",
            replacement="NewName",
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is True
        assert "NewName" in target.read_text(encoding="utf-8")


class TestApplyScriptRuleRegex:
    """正则表达式匹配替换"""

    def test_regex_replacement(self, engine, tmp_path):
        target = tmp_path / "test.txt"
        target.write_text("version=1.2.3", encoding="utf-8")

        rule = ScriptRule(
            target_path="test.txt",
            pattern=r"\d+\.\d+\.\d+",
            replacement="9.9.9",
            use_regex=True,
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_text(encoding="utf-8") == "version=9.9.9"

    def test_regex_with_groups(self, engine, tmp_path):
        target = tmp_path / "test.txt"
        target.write_text("name=Alice age=30", encoding="utf-8")

        rule = ScriptRule(
            target_path="test.txt",
            pattern=r"name=(\w+)",
            replacement=r"name=Bob",
            use_regex=True,
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is True
        assert "name=Bob" in target.read_text(encoding="utf-8")

    def test_regex_multiple_matches(self, engine, tmp_path):
        target = tmp_path / "test.txt"
        target.write_text("foo123 bar456 baz789", encoding="utf-8")

        rule = ScriptRule(
            target_path="test.txt",
            pattern=r"\d+",
            replacement="000",
            use_regex=True,
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_text(encoding="utf-8") == "foo000 bar000 baz000"


class TestApplyScriptRuleFileNotFound:
    """目标文件不存在"""

    def test_missing_file_returns_failure(self, engine, tmp_path):
        rule = ScriptRule(
            target_path="nonexistent.txt", pattern="x", replacement="y"
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is False
        assert "不存在" in result.message

    def test_missing_nested_file(self, engine, tmp_path):
        rule = ScriptRule(
            target_path="deep/nested/missing.txt", pattern="x", replacement="y"
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is False


class TestApplyScriptRuleEdgeCases:
    """边界情况"""

    def test_empty_file(self, engine, tmp_path):
        target = tmp_path / "empty.txt"
        target.write_text("", encoding="utf-8")

        rule = ScriptRule(
            target_path="empty.txt", pattern="anything", replacement="something"
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_text(encoding="utf-8") == ""

    def test_replacement_with_empty_string(self, engine, tmp_path):
        target = tmp_path / "test.txt"
        target.write_text("remove this word", encoding="utf-8")

        rule = ScriptRule(
            target_path="test.txt", pattern="this ", replacement=""
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_text(encoding="utf-8") == "remove word"

    def test_rule_index_defaults_to_zero(self, engine, tmp_path):
        target = tmp_path / "test.txt"
        target.write_text("content", encoding="utf-8")

        rule = ScriptRule(
            target_path="test.txt", pattern="content", replacement="new"
        )
        result = engine.apply_script_rule(tmp_path, rule)

        assert result.rule_index == 0
