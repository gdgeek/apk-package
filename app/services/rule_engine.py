"""Rule Engine - 规则验证与执行"""

import base64
import re
from pathlib import Path, PurePosixPath

from app.models.schemas import (
    ImageRule,
    ReplacementRule,
    RuleResult,
    ScriptRule,
    ValidationError,
    ValidationResult,
)


class RuleEngine:
    """规则引擎：负责验证和执行替换规则"""

    def validate_rules(self, rules: list[ReplacementRule]) -> ValidationResult:
        """验证规则集合，返回每条规则的验证结果"""
        errors: list[ValidationError] = []

        for index, rule in enumerate(rules):
            errors.extend(self._validate_target_path(index, rule.target_path))

            if isinstance(rule, ScriptRule):
                errors.extend(self._validate_script_rule(index, rule))
            elif isinstance(rule, ImageRule):
                errors.extend(self._validate_image_rule(index, rule))

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def _validate_target_path(
        self, rule_index: int, target_path: str
    ) -> list[ValidationError]:
        """验证 target_path 字段"""
        errors: list[ValidationError] = []

        if not target_path or not target_path.strip():
            errors.append(
                ValidationError(
                    rule_index=rule_index,
                    field="target_path",
                    message="target_path 不能为空",
                )
            )
            return errors

        if ".." in target_path:
            errors.append(
                ValidationError(
                    rule_index=rule_index,
                    field="target_path",
                    message="target_path 不能包含 '..' 路径遍历",
                )
            )

        if target_path.startswith("/"):
            errors.append(
                ValidationError(
                    rule_index=rule_index,
                    field="target_path",
                    message="target_path 必须是相对路径，不能以 '/' 开头",
                )
            )

        return errors

    def _validate_script_rule(
        self, rule_index: int, rule: ScriptRule
    ) -> list[ValidationError]:
        """验证 ScriptRule 特有字段"""
        errors: list[ValidationError] = []

        if not rule.pattern or not rule.pattern.strip():
            errors.append(
                ValidationError(
                    rule_index=rule_index,
                    field="pattern",
                    message="pattern 不能为空",
                )
            )
            return errors

        if rule.use_regex:
            try:
                re.compile(rule.pattern)
            except re.error as e:
                errors.append(
                    ValidationError(
                        rule_index=rule_index,
                        field="pattern",
                        message=f"无效的正则表达式: {e}",
                    )
                )

        return errors

    def _validate_image_rule(
        self, rule_index: int, rule: ImageRule
    ) -> list[ValidationError]:
        """验证 ImageRule 特有字段"""
        errors: list[ValidationError] = []

        if not rule.image_data or not rule.image_data.strip():
            errors.append(
                ValidationError(
                    rule_index=rule_index,
                    field="image_data",
                    message="image_data 不能为空",
                )
            )
            return errors

        try:
            base64.b64decode(rule.image_data, validate=True)
        except Exception:
            errors.append(
                ValidationError(
                    rule_index=rule_index,
                    field="image_data",
                    message="image_data 不是有效的 Base64 编码",
                )
            )

        return errors

    def apply_script_rule(self, base_dir: Path, rule: ScriptRule) -> RuleResult:
        """在工作副本目录中执行脚本替换规则"""
        target_file = base_dir / rule.target_path

        if not target_file.exists():
            return RuleResult(
                rule_index=0,
                success=False,
                message=f"目标文件不存在: {rule.target_path}",
            )

        try:
            content = target_file.read_text(encoding="utf-8")

            if rule.use_regex:
                new_content = re.sub(rule.pattern, rule.replacement, content)
            else:
                new_content = content.replace(rule.pattern, rule.replacement)

            target_file.write_text(new_content, encoding="utf-8")

            return RuleResult(
                rule_index=0,
                success=True,
                message=f"脚本替换成功: {rule.target_path}",
            )
        except Exception as e:
            return RuleResult(
                rule_index=0,
                success=False,
                message=f"脚本替换失败: {rule.target_path}, 错误: {e}",
            )

    def apply_image_rule(self, base_dir: Path, rule: ImageRule) -> RuleResult:
        """在工作副本目录中执行图片替换规则"""
        target_file = base_dir / rule.target_path

        if not target_file.exists():
            return RuleResult(
                rule_index=0,
                success=False,
                message=f"目标文件不存在: {rule.target_path}",
            )

        try:
            image_bytes = base64.b64decode(rule.image_data)
            target_file.write_bytes(image_bytes)

            return RuleResult(
                rule_index=0,
                success=True,
                message=f"图片替换成功: {rule.target_path}",
            )
        except Exception as e:
            return RuleResult(
                rule_index=0,
                success=False,
                message=f"图片替换失败: {rule.target_path}, 错误: {e}",
            )


