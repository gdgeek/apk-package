"""Tests for APK Processor - 反编译、缓存复制与重新打包"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.apk_processor import APKProcessor


@pytest.fixture
def processor():
    return APKProcessor()


# === decompile_to_cache tests ===


@pytest.mark.asyncio
async def test_decompile_to_cache_success(processor, tmp_path):
    """apktool 成功时不抛异常，且传入正确参数"""
    apk_path = tmp_path / "test.apk"
    apk_path.write_bytes(b"fake apk content")
    cache_dir = tmp_path / "cache" / "abc123"

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"success output", b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        await processor.decompile_to_cache(apk_path, cache_dir)

        mock_exec.assert_called_once_with(
            "apktool", "d", str(apk_path), "-o", str(cache_dir / "decompiled"), "-f",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    # cache_dir should have been created
    assert cache_dir.exists()


@pytest.mark.asyncio
async def test_decompile_to_cache_failure(processor, tmp_path):
    """apktool 失败时抛出 RuntimeError"""
    apk_path = tmp_path / "test.apk"
    apk_path.write_bytes(b"fake apk content")
    cache_dir = tmp_path / "cache" / "abc123"

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"brut.androlib.err: Could not decode")
    mock_process.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(RuntimeError, match="apktool 反编译失败"):
            await processor.decompile_to_cache(apk_path, cache_dir)


@pytest.mark.asyncio
async def test_decompile_to_cache_creates_cache_dir(processor, tmp_path):
    """decompile_to_cache 应自动创建缓存目录"""
    apk_path = tmp_path / "test.apk"
    apk_path.write_bytes(b"fake")
    cache_dir = tmp_path / "deep" / "nested" / "cache"

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        await processor.decompile_to_cache(apk_path, cache_dir)

    assert cache_dir.exists()


# === copy_cache_to_workdir tests ===


@pytest.mark.asyncio
async def test_copy_cache_to_workdir_copies_files(processor, tmp_path):
    """copy_cache_to_workdir 应完整复制目录结构和文件内容"""
    # Set up source cache directory
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "decompiled").mkdir()
    (cache_dir / "decompiled" / "AndroidManifest.xml").write_text("<manifest/>")
    (cache_dir / "decompiled" / "res").mkdir()
    (cache_dir / "decompiled" / "res" / "values").mkdir()
    (cache_dir / "decompiled" / "res" / "values" / "strings.xml").write_text("<resources/>")
    (cache_dir / "decompiled" / "smali").mkdir()
    (cache_dir / "decompiled" / "smali" / "Main.smali").write_text(".class public LMain;")

    work_dir = tmp_path / "workspace" / "task001"

    await processor.copy_cache_to_workdir(cache_dir, work_dir)

    # Verify all files were copied
    assert (work_dir / "decompiled" / "AndroidManifest.xml").read_text() == "<manifest/>"
    assert (work_dir / "decompiled" / "res" / "values" / "strings.xml").read_text() == "<resources/>"
    assert (work_dir / "decompiled" / "smali" / "Main.smali").read_text() == ".class public LMain;"


@pytest.mark.asyncio
async def test_copy_cache_to_workdir_does_not_modify_source(processor, tmp_path):
    """copy_cache_to_workdir 不应修改源缓存目录"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "file.txt").write_text("original content")

    work_dir = tmp_path / "work"

    await processor.copy_cache_to_workdir(cache_dir, work_dir)

    # Modify the work copy
    (work_dir / "file.txt").write_text("modified content")

    # Source should be unchanged
    assert (cache_dir / "file.txt").read_text() == "original content"


@pytest.mark.asyncio
async def test_copy_cache_to_workdir_fails_if_source_missing(processor, tmp_path):
    """源目录不存在时应抛出 RuntimeError"""
    cache_dir = tmp_path / "nonexistent"
    work_dir = tmp_path / "work"

    with pytest.raises(RuntimeError, match="复制缓存到工作目录失败"):
        await processor.copy_cache_to_workdir(cache_dir, work_dir)


@pytest.mark.asyncio
async def test_copy_cache_to_workdir_fails_if_dest_exists(processor, tmp_path):
    """目标目录已存在时应抛出 RuntimeError"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "file.txt").write_text("content")

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    with pytest.raises(RuntimeError, match="复制缓存到工作目录失败"):
        await processor.copy_cache_to_workdir(cache_dir, work_dir)


# === recompile tests ===


@pytest.mark.asyncio
async def test_recompile_success(processor, tmp_path):
    """apktool b 成功时不抛异常，且传入正确参数"""
    source_dir = tmp_path / "workspace" / "task001" / "decompiled"
    source_dir.mkdir(parents=True)
    output_apk = tmp_path / "output" / "task001.apk"

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"built successfully", b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        await processor.recompile(source_dir, output_apk)

        mock_exec.assert_called_once_with(
            "apktool", "b", str(source_dir), "-o", str(output_apk),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    # output parent dir should have been created
    assert output_apk.parent.exists()


@pytest.mark.asyncio
async def test_recompile_failure(processor, tmp_path):
    """apktool b 失败时抛出 RuntimeError"""
    source_dir = tmp_path / "workspace" / "task001" / "decompiled"
    source_dir.mkdir(parents=True)
    output_apk = tmp_path / "output" / "task001.apk"

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"Error: missing apktool.yml")
    mock_process.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(RuntimeError, match="apktool 重新打包失败"):
            await processor.recompile(source_dir, output_apk)


@pytest.mark.asyncio
async def test_recompile_creates_output_parent_dir(processor, tmp_path):
    """recompile 应自动创建输出文件的父目录"""
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    output_apk = tmp_path / "deep" / "nested" / "output.apk"

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        await processor.recompile(source_dir, output_apk)

    assert output_apk.parent.exists()


@pytest.mark.asyncio
async def test_recompile_error_includes_stderr(processor, tmp_path):
    """RuntimeError 应包含 stderr 中的错误信息"""
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    output_apk = tmp_path / "out.apk"

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"specific error detail here")
    mock_process.returncode = 2

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(RuntimeError, match="specific error detail here"):
            await processor.recompile(source_dir, output_apk)
