"""APK Processor - APK 反编译、缓存复制与重新打包"""

import asyncio
import shutil
from pathlib import Path

from app.models.schemas import FileNode, ImageRule, ReplacementRule, RuleResult, ScriptRule
from app.services.rule_engine import RuleEngine


class APKProcessor:
    """APK 处理器：负责反编译、缓存管理和重新打包"""

    async def decompile_to_cache(self, apk_path: Path, cache_dir: Path) -> None:
        """使用 apktool 反编译 APK 到缓存目录（上传时调用）。

        运行: apktool d {apk_path} -o {cache_dir}/decompiled -f

        Args:
            apk_path: 原始 APK 文件路径
            cache_dir: 缓存根目录 (data/cache/{apk_id}/)

        Raises:
            RuntimeError: apktool 命令执行失败
        """
        output_dir = cache_dir / "decompiled"
        cache_dir.mkdir(parents=True, exist_ok=True)

        process = await asyncio.create_subprocess_exec(
            "apktool", "d", str(apk_path), "-o", str(output_dir), "-f",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"apktool 反编译失败 (exit code {process.returncode}): {error_msg}"
            )

    async def copy_cache_to_workdir(self, cache_dir: Path, work_dir: Path) -> None:
        """从缓存目录复制一份工作副本（创建任务时调用）。

        使用 shutil.copytree 在 executor 中运行，避免阻塞事件循环。

        Args:
            cache_dir: 缓存目录 (data/cache/{apk_id}/)
            work_dir: 工作副本目录 (data/workspace/{task_id}/)

        Raises:
            RuntimeError: 复制操作失败
        """
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                shutil.copytree,
                str(cache_dir),
                str(work_dir),
            )
        except Exception as e:
            raise RuntimeError(f"复制缓存到工作目录失败: {e}") from e

    async def recompile(self, source_dir: Path, output_apk: Path) -> None:
        """使用 apktool 重新打包 APK。

        运行: apktool b {source_dir} -o {output_apk}

        Args:
            source_dir: 反编译后的源目录
            output_apk: 输出 APK 文件路径

        Raises:
            RuntimeError: apktool 命令执行失败
        """
        output_apk.parent.mkdir(parents=True, exist_ok=True)

        process = await asyncio.create_subprocess_exec(
            "apktool", "b", str(source_dir), "-o", str(output_apk),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"apktool 重新打包失败 (exit code {process.returncode}): {error_msg}"
            )

    def list_files_from_cache(self, cache_dir: Path) -> list[FileNode]:
        """从缓存目录读取文件结构，构建 FileNode 树。

        Args:
            cache_dir: 缓存根目录 (data/cache/{apk_id}/)

        Returns:
            FileNode 树的根节点列表（decompiled 目录下的顶层条目）
        """
        decompiled_dir = cache_dir / "decompiled"
        if not decompiled_dir.is_dir():
            return []

        def build_tree(directory: Path, base: Path) -> list[FileNode]:
            nodes: list[FileNode] = []
            try:
                entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except OSError:
                return nodes

            for entry in entries:
                rel_path = str(entry.relative_to(base))
                if entry.is_dir():
                    children = build_tree(entry, base)
                    nodes.append(FileNode(
                        name=entry.name,
                        path=rel_path,
                        is_directory=True,
                        children=children,
                    ))
                else:
                    nodes.append(FileNode(
                        name=entry.name,
                        path=rel_path,
                        is_directory=False,
                        size=entry.stat().st_size,
                    ))
            return nodes

        return build_tree(decompiled_dir, decompiled_dir)

    def read_file_from_cache(self, cache_dir: Path, internal_path: str) -> str:
        """从缓存目录读取指定文件的文本内容。

        Args:
            cache_dir: 缓存根目录 (data/cache/{apk_id}/)
            internal_path: APK 内部相对路径 (e.g. "res/values/strings.xml")

        Returns:
            文件的 UTF-8 文本内容

        Raises:
            ValueError: 路径包含遍历攻击或为绝对路径
            FileNotFoundError: 文件不存在
        """
        if ".." in internal_path:
            raise ValueError("路径不允许包含 '..'")
        if internal_path.startswith("/"):
            raise ValueError("路径不允许以 '/' 开头")

        target = cache_dir / "decompiled" / internal_path
        # Resolve and verify the target is still within the decompiled directory
        decompiled_dir = (cache_dir / "decompiled").resolve()
        resolved_target = target.resolve()
        if not str(resolved_target).startswith(str(decompiled_dir)):
            raise ValueError("路径遍历攻击被阻止")

        if not resolved_target.is_file():
            raise FileNotFoundError(f"文件不存在: {internal_path}")

        return resolved_target.read_text(encoding="utf-8")

    async def process_task(
        self,
        cache_dir: Path,
        work_dir: Path,
        output_path: Path,
        rules: list[ReplacementRule],
    ) -> list[RuleResult]:
        """执行完整的修改任务：复制缓存 → 应用规则 → 重新打包。

        Args:
            cache_dir: 缓存目录 (data/cache/{apk_id}/)
            work_dir: 工作副本目录 (data/workspace/{task_id}/)
            output_path: 输出 APK 文件路径
            rules: 替换规则列表

        Returns:
            每条规则的执行结果列表

        Raises:
            RuntimeError: 复制缓存或重新打包失败时抛出，并清理工作目录
        """
        try:
            # Step 1: 复制缓存到工作目录
            await self.copy_cache_to_workdir(cache_dir, work_dir)
        except Exception:
            # 复制失败时清理工作目录
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

        # Step 2: 在工作副本上依次应用规则
        rule_engine = RuleEngine()
        decompiled_dir = work_dir / "decompiled"
        rule_results: list[RuleResult] = []

        for index, rule in enumerate(rules):
            if isinstance(rule, ScriptRule):
                result = rule_engine.apply_script_rule(decompiled_dir, rule)
            elif isinstance(rule, ImageRule):
                result = rule_engine.apply_image_rule(decompiled_dir, rule)
            else:
                result = RuleResult(
                    rule_index=index,
                    success=False,
                    message=f"未知的规则类型: {type(rule).__name__}",
                )
            # 设置正确的 rule_index
            result.rule_index = index
            rule_results.append(result)

        # Step 3: 重新打包
        try:
            await self.recompile(decompiled_dir, output_path)
        except Exception:
            # 重新打包失败时清理工作目录
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

        return rule_results
