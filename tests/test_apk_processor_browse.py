"""Tests for APKProcessor cache browsing functionality (list_files_from_cache, read_file_from_cache)."""

import pytest
from pathlib import Path

from app.services.apk_processor import APKProcessor
from app.models.schemas import FileNode


@pytest.fixture
def processor():
    return APKProcessor()


@pytest.fixture
def cache_dir(tmp_path):
    """Create a cache directory with a sample decompiled structure."""
    decompiled = tmp_path / "decompiled"
    decompiled.mkdir()

    # Create directory structure:
    # res/
    #   values/
    #     strings.xml
    #   drawable/
    #     icon.png
    # AndroidManifest.xml
    # smali/
    #   com/
    #     example/
    #       Main.smali

    (decompiled / "res" / "values").mkdir(parents=True)
    (decompiled / "res" / "drawable").mkdir(parents=True)
    (decompiled / "smali" / "com" / "example").mkdir(parents=True)

    (decompiled / "AndroidManifest.xml").write_text("<manifest/>", encoding="utf-8")
    (decompiled / "res" / "values" / "strings.xml").write_text(
        '<resources><string name="app_name">Test</string></resources>', encoding="utf-8"
    )
    (decompiled / "res" / "drawable" / "icon.png").write_bytes(b"\x89PNG fake")
    (decompiled / "smali" / "com" / "example" / "Main.smali").write_text(
        ".class public Lcom/example/Main;", encoding="utf-8"
    )

    return tmp_path


# === list_files_from_cache tests ===


class TestListFilesFromCache:
    def test_returns_tree_structure(self, processor, cache_dir):
        nodes = processor.list_files_from_cache(cache_dir)
        names = [n.name for n in nodes]
        # Directories should come first, sorted alphabetically
        assert "res" in names
        assert "smali" in names
        assert "AndroidManifest.xml" in names

    def test_directories_sorted_before_files(self, processor, cache_dir):
        nodes = processor.list_files_from_cache(cache_dir)
        dir_indices = [i for i, n in enumerate(nodes) if n.is_directory]
        file_indices = [i for i, n in enumerate(nodes) if not n.is_directory]
        if dir_indices and file_indices:
            assert max(dir_indices) < min(file_indices)

    def test_directory_nodes_have_children(self, processor, cache_dir):
        nodes = processor.list_files_from_cache(cache_dir)
        res_node = next(n for n in nodes if n.name == "res")
        assert res_node.is_directory
        assert len(res_node.children) == 2  # drawable, values
        child_names = [c.name for c in res_node.children]
        assert "drawable" in child_names
        assert "values" in child_names

    def test_file_nodes_have_size(self, processor, cache_dir):
        nodes = processor.list_files_from_cache(cache_dir)
        manifest = next(n for n in nodes if n.name == "AndroidManifest.xml")
        assert not manifest.is_directory
        assert manifest.size is not None
        assert manifest.size > 0

    def test_paths_are_relative_to_decompiled(self, processor, cache_dir):
        nodes = processor.list_files_from_cache(cache_dir)
        res_node = next(n for n in nodes if n.name == "res")
        assert res_node.path == "res"
        values_node = next(c for c in res_node.children if c.name == "values")
        assert values_node.path == "res/values"
        strings_node = next(c for c in values_node.children if c.name == "strings.xml")
        assert strings_node.path == "res/values/strings.xml"

    def test_empty_decompiled_dir(self, processor, tmp_path):
        decompiled = tmp_path / "decompiled"
        decompiled.mkdir()
        nodes = processor.list_files_from_cache(tmp_path)
        assert nodes == []

    def test_missing_decompiled_dir(self, processor, tmp_path):
        nodes = processor.list_files_from_cache(tmp_path)
        assert nodes == []

    def test_nested_directory_structure(self, processor, cache_dir):
        nodes = processor.list_files_from_cache(cache_dir)
        smali_node = next(n for n in nodes if n.name == "smali")
        com_node = smali_node.children[0]
        assert com_node.name == "com"
        example_node = com_node.children[0]
        assert example_node.name == "example"
        main_node = example_node.children[0]
        assert main_node.name == "Main.smali"
        assert main_node.path == "smali/com/example/Main.smali"


# === read_file_from_cache tests ===


class TestReadFileFromCache:
    def test_read_existing_file(self, processor, cache_dir):
        content = processor.read_file_from_cache(cache_dir, "AndroidManifest.xml")
        assert content == "<manifest/>"

    def test_read_nested_file(self, processor, cache_dir):
        content = processor.read_file_from_cache(cache_dir, "res/values/strings.xml")
        assert "app_name" in content

    def test_file_not_found_raises(self, processor, cache_dir):
        with pytest.raises(FileNotFoundError):
            processor.read_file_from_cache(cache_dir, "nonexistent.xml")

    def test_path_traversal_dotdot_rejected(self, processor, cache_dir):
        with pytest.raises(ValueError, match="\\.\\."):
            processor.read_file_from_cache(cache_dir, "../etc/passwd")

    def test_path_traversal_middle_dotdot_rejected(self, processor, cache_dir):
        with pytest.raises(ValueError, match="\\.\\."):
            processor.read_file_from_cache(cache_dir, "res/../../etc/passwd")

    def test_absolute_path_rejected(self, processor, cache_dir):
        with pytest.raises(ValueError, match="/"):
            processor.read_file_from_cache(cache_dir, "/etc/passwd")

    def test_directory_path_raises_not_found(self, processor, cache_dir):
        with pytest.raises(FileNotFoundError):
            processor.read_file_from_cache(cache_dir, "res/values")

    def test_read_deeply_nested_file(self, processor, cache_dir):
        content = processor.read_file_from_cache(cache_dir, "smali/com/example/Main.smali")
        assert "Lcom/example/Main" in content
