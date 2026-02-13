"""Tests for APKProcessor.process_task() - 完整修改任务流程"""

import asyncio
import base64
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import ImageRule, RuleResult, ScriptRule
from app.services.apk_processor import APKProcessor


@pytest.fixture
def processor():
    return APKProcessor()


@pytest.fixture
def cache_dir(tmp_path):
    """Create a cache directory with a sample decompiled structure."""
    cache = tmp_path / "cache"
    decompiled = cache / "decompiled"
    decompiled.mkdir(parents=True)

    # Create sample files
    (decompiled / "AndroidManifest.xml").write_text(
        '<manifest package="com.example.app"/>', encoding="utf-8"
    )
    (decompiled / "res").mkdir()
    (decompiled / "res" / "values").mkdir()
    (decompiled / "res" / "values" / "strings.xml").write_text(
        '<resources><string name="app_name">OldName</string></resources>',
        encoding="utf-8",
    )
    (decompiled / "res" / "drawable").mkdir()
    (decompiled / "res" / "drawable" / "icon.png").write_bytes(b"\x89PNG old icon")

    return cache


@pytest.fixture
def work_dir(tmp_path):
    return tmp_path / "workspace" / "task001"


@pytest.fixture
def output_path(tmp_path):
    return tmp_path / "output" / "task001.apk"


def _mock_recompile_success():
    """Return a mock for recompile that succeeds."""
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"")
    mock_process.returncode = 0
    return mock_process


# === process_task: happy path ===


@pytest.mark.asyncio
async def test_process_task_copies_cache_and_applies_script_rule(
    processor, cache_dir, work_dir, output_path
):
    """process_task should copy cache, apply script rules, and recompile."""
    rules = [
        ScriptRule(
            target_path="res/values/strings.xml",
            pattern="OldName",
            replacement="NewName",
        )
    ]

    with patch("asyncio.create_subprocess_exec", return_value=_mock_recompile_success()):
        results = await processor.process_task(cache_dir, work_dir, output_path, rules)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].rule_index == 0

    # Verify the file was actually modified in the work dir
    modified = (work_dir / "decompiled" / "res" / "values" / "strings.xml").read_text(
        encoding="utf-8"
    )
    assert "NewName" in modified
    assert "OldName" not in modified


@pytest.mark.asyncio
async def test_process_task_applies_image_rule(
    processor, cache_dir, work_dir, output_path
):
    """process_task should apply image replacement rules."""
    new_image_data = base64.b64encode(b"\x89PNG new icon data").decode()
    rules = [
        ImageRule(
            target_path="res/drawable/icon.png",
            image_data=new_image_data,
        )
    ]

    with patch("asyncio.create_subprocess_exec", return_value=_mock_recompile_success()):
        results = await processor.process_task(cache_dir, work_dir, output_path, rules)

    assert len(results) == 1
    assert results[0].success is True

    # Verify the image was replaced
    replaced = (work_dir / "decompiled" / "res" / "drawable" / "icon.png").read_bytes()
    assert replaced == b"\x89PNG new icon data"


@pytest.mark.asyncio
async def test_process_task_applies_multiple_rules_in_order(
    processor, cache_dir, work_dir, output_path
):
    """process_task should apply multiple rules sequentially with correct indices."""
    new_image_data = base64.b64encode(b"replaced").decode()
    rules = [
        ScriptRule(
            target_path="res/values/strings.xml",
            pattern="OldName",
            replacement="NewName",
        ),
        ImageRule(
            target_path="res/drawable/icon.png",
            image_data=new_image_data,
        ),
        ScriptRule(
            target_path="AndroidManifest.xml",
            pattern="com.example.app",
            replacement="com.modified.app",
        ),
    ]

    with patch("asyncio.create_subprocess_exec", return_value=_mock_recompile_success()):
        results = await processor.process_task(cache_dir, work_dir, output_path, rules)

    assert len(results) == 3
    for i, result in enumerate(results):
        assert result.rule_index == i
        assert result.success is True

    # Verify all modifications applied
    manifest = (work_dir / "decompiled" / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert "com.modified.app" in manifest


@pytest.mark.asyncio
async def test_process_task_empty_rules(processor, cache_dir, work_dir, output_path):
    """process_task with no rules should still copy and recompile."""
    with patch("asyncio.create_subprocess_exec", return_value=_mock_recompile_success()):
        results = await processor.process_task(cache_dir, work_dir, output_path, [])

    assert results == []
    # Work dir should exist with copied files
    assert (work_dir / "decompiled" / "AndroidManifest.xml").exists()


# === process_task: rule failure continues ===


@pytest.mark.asyncio
async def test_process_task_continues_on_rule_failure(
    processor, cache_dir, work_dir, output_path
):
    """When a rule targets a nonexistent file, it should fail but other rules continue."""
    rules = [
        ScriptRule(
            target_path="nonexistent.txt",
            pattern="foo",
            replacement="bar",
        ),
        ScriptRule(
            target_path="res/values/strings.xml",
            pattern="OldName",
            replacement="NewName",
        ),
    ]

    with patch("asyncio.create_subprocess_exec", return_value=_mock_recompile_success()):
        results = await processor.process_task(cache_dir, work_dir, output_path, rules)

    assert len(results) == 2
    assert results[0].success is False
    assert results[0].rule_index == 0
    assert results[1].success is True
    assert results[1].rule_index == 1


@pytest.mark.asyncio
async def test_process_task_all_rules_fail_still_recompiles(
    processor, cache_dir, work_dir, output_path
):
    """Even if all rules fail, recompile should still be attempted."""
    rules = [
        ScriptRule(target_path="missing1.txt", pattern="a", replacement="b"),
        ScriptRule(target_path="missing2.txt", pattern="c", replacement="d"),
    ]

    with patch("asyncio.create_subprocess_exec", return_value=_mock_recompile_success()) as mock_exec:
        results = await processor.process_task(cache_dir, work_dir, output_path, rules)

    assert all(not r.success for r in results)
    # recompile was still called
    mock_exec.assert_called_once()


# === process_task: cache does not change ===


@pytest.mark.asyncio
async def test_process_task_does_not_modify_cache(
    processor, cache_dir, work_dir, output_path
):
    """Cache directory must remain unchanged after process_task."""
    original_content = (cache_dir / "decompiled" / "res" / "values" / "strings.xml").read_text(
        encoding="utf-8"
    )
    original_icon = (cache_dir / "decompiled" / "res" / "drawable" / "icon.png").read_bytes()

    new_image = base64.b64encode(b"new").decode()
    rules = [
        ScriptRule(
            target_path="res/values/strings.xml",
            pattern="OldName",
            replacement="NewName",
        ),
        ImageRule(target_path="res/drawable/icon.png", image_data=new_image),
    ]

    with patch("asyncio.create_subprocess_exec", return_value=_mock_recompile_success()):
        await processor.process_task(cache_dir, work_dir, output_path, rules)

    # Cache must be untouched
    assert (cache_dir / "decompiled" / "res" / "values" / "strings.xml").read_text(
        encoding="utf-8"
    ) == original_content
    assert (cache_dir / "decompiled" / "res" / "drawable" / "icon.png").read_bytes() == original_icon


# === process_task: cleanup on failure ===


@pytest.mark.asyncio
async def test_process_task_cleans_workdir_on_copy_failure(processor, tmp_path):
    """If copy_cache_to_workdir fails, work_dir should be cleaned up."""
    cache_dir = tmp_path / "nonexistent_cache"
    work_dir = tmp_path / "workspace" / "task_fail"
    output_path = tmp_path / "output" / "fail.apk"

    with pytest.raises(RuntimeError, match="复制缓存到工作目录失败"):
        await processor.process_task(cache_dir, work_dir, output_path, [])

    assert not work_dir.exists()


@pytest.mark.asyncio
async def test_process_task_cleans_workdir_on_recompile_failure(
    processor, cache_dir, work_dir, output_path
):
    """If recompile fails, work_dir should be cleaned up and error re-raised."""
    rules = [
        ScriptRule(
            target_path="res/values/strings.xml",
            pattern="OldName",
            replacement="NewName",
        )
    ]

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"recompile error detail")
    mock_process.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(RuntimeError, match="apktool 重新打包失败"):
            await processor.process_task(cache_dir, work_dir, output_path, rules)

    # Work dir should have been cleaned up
    assert not work_dir.exists()


# === process_task: regex script rule ===


@pytest.mark.asyncio
async def test_process_task_regex_script_rule(
    processor, cache_dir, work_dir, output_path
):
    """process_task should support regex-based script rules."""
    rules = [
        ScriptRule(
            target_path="res/values/strings.xml",
            pattern=r"name=\"app_name\">(\w+)<",
            replacement='name="app_name">ReplacedApp<',
            use_regex=True,
        )
    ]

    with patch("asyncio.create_subprocess_exec", return_value=_mock_recompile_success()):
        results = await processor.process_task(cache_dir, work_dir, output_path, rules)

    assert results[0].success is True
    content = (work_dir / "decompiled" / "res" / "values" / "strings.xml").read_text(
        encoding="utf-8"
    )
    assert "ReplacedApp" in content
