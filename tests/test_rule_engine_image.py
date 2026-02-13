"""RuleEngine.apply_image_rule() 单元测试"""

import base64

import pytest

from app.models.schemas import ImageRule
from app.services.rule_engine import RuleEngine


@pytest.fixture
def engine():
    return RuleEngine()


def _encode(data: bytes) -> str:
    """Helper: encode bytes to Base64 string."""
    return base64.b64encode(data).decode("ascii")


class TestApplyImageRuleSuccess:
    """图片替换成功场景"""

    def test_simple_replacement(self, engine, tmp_path):
        target = tmp_path / "icon.png"
        target.write_bytes(b"old image data")

        new_data = b"\x89PNG\r\n\x1a\n fake png content"
        rule = ImageRule(target_path="icon.png", image_data=_encode(new_data))
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_bytes() == new_data

    def test_nested_path(self, engine, tmp_path):
        subdir = tmp_path / "res" / "drawable"
        subdir.mkdir(parents=True)
        target = subdir / "logo.png"
        target.write_bytes(b"original")

        new_data = b"replaced image bytes"
        rule = ImageRule(
            target_path="res/drawable/logo.png", image_data=_encode(new_data)
        )
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_bytes() == new_data

    def test_binary_content_preserved(self, engine, tmp_path):
        """验证任意二进制数据（含 null 字节）能正确写入"""
        target = tmp_path / "img.bin"
        target.write_bytes(b"old")

        new_data = bytes(range(256))  # 0x00 ~ 0xFF
        rule = ImageRule(target_path="img.bin", image_data=_encode(new_data))
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_bytes() == new_data

    def test_result_message_contains_path(self, engine, tmp_path):
        target = tmp_path / "pic.jpg"
        target.write_bytes(b"jpeg")

        rule = ImageRule(target_path="pic.jpg", image_data=_encode(b"new"))
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is True
        assert "pic.jpg" in result.message

    def test_rule_index_defaults_to_zero(self, engine, tmp_path):
        target = tmp_path / "x.png"
        target.write_bytes(b"data")

        rule = ImageRule(target_path="x.png", image_data=_encode(b"new"))
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.rule_index == 0


class TestApplyImageRuleFileNotFound:
    """目标文件不存在"""

    def test_missing_file_returns_failure(self, engine, tmp_path):
        rule = ImageRule(
            target_path="nonexistent.png", image_data=_encode(b"data")
        )
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is False
        assert "不存在" in result.message

    def test_missing_nested_file(self, engine, tmp_path):
        rule = ImageRule(
            target_path="deep/nested/missing.png", image_data=_encode(b"data")
        )
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is False

    def test_failure_message_contains_path(self, engine, tmp_path):
        rule = ImageRule(
            target_path="res/drawable/gone.png", image_data=_encode(b"x")
        )
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is False
        assert "res/drawable/gone.png" in result.message


class TestApplyImageRuleEdgeCases:
    """边界情况"""

    def test_empty_image_data(self, engine, tmp_path):
        """空的 Base64 解码为空字节，应成功写入"""
        target = tmp_path / "empty.png"
        target.write_bytes(b"old content")

        rule = ImageRule(target_path="empty.png", image_data=_encode(b""))
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_bytes() == b""

    def test_large_image_data(self, engine, tmp_path):
        """较大的二进制数据也能正确替换"""
        target = tmp_path / "big.png"
        target.write_bytes(b"small")

        new_data = b"\xab" * 100_000
        rule = ImageRule(target_path="big.png", image_data=_encode(new_data))
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is True
        assert target.read_bytes() == new_data

    def test_invalid_base64_returns_failure(self, engine, tmp_path):
        """无效的 Base64 数据应返回失败"""
        target = tmp_path / "img.png"
        target.write_bytes(b"original")

        rule = ImageRule(target_path="img.png", image_data="!!!not-base64!!!")
        result = engine.apply_image_rule(tmp_path, rule)

        assert result.success is False
        assert "img.png" in result.message
