"""GuardrailMiddleware - 输出内容护栏（PII/敏感数据/格式校验）.

中间件 #10 in ARW middleware chain (after_model chain 最末位):
- LLM 输出 PII / 敏感数据脱敏
- 工具产出物字段与格式校验
- 结构化输出 schema 校验 + 自动重试
- 护栏违规事件上报

与 HITL 的"行为审批"正交，负责输出内容侧的护栏。
严重违规可触发 HITL，由人工裁决是否继续执行.
"""

from __future__ import annotations

import json
import logging
import re
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from deerflow.agents.worker_state import WorkerState

logger = logging.getLogger(__name__)


class GuardrailMiddleware(AgentMiddleware[WorkerState]):
    """Content guardrails for output safety and format compliance.

    This middleware provides content-side guardrails:
    1. PII (Personally Identifiable Information) detection and masking
    2. Sensitive data detection and masking
    3. Structured output (JSON) schema validation with auto-retry
    4. Artifact field and format validation

    Position: LAST in after_model chain (acts on final output before delivery).

    Violations can trigger alerts via EventReportMiddleware and escalate
    to HITL for human review on severe violations.
    """

    state_schema = WorkerState

    # PII patterns for detection
    PII_PATTERNS = {
        "email": re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        ),
        "phone": re.compile(
            r"\b(?:\+?86)?1[3-9]\d{9}\b|\b\d{3}-\d{4}-\d{4}\b"
        ),
        "id_card": re.compile(
            r"\b\d{17}[\dXx]|\d{15}\b"
        ),
        "credit_card": re.compile(
            r"\b(?:\d{4}[- ]?){3}\d{4}\b"
        ),
    }

    # Sensitive keywords for detection
    SENSITIVE_KEYWORDS = [
        "password",
        "secret",
        "token",
        "key",
        "credential",
        "api_key",
        "private_key",
    ]

    def __init__(
        self,
        enable_pii_detection: bool = True,
        enable_sensitive_detection: bool = True,
        enable_schema_validation: bool = True,
        pii_action: str = "mask",  # "mask", "block", "alert"
        sensitive_action: str = "mask",  # "mask", "block", "alert"
        schema_validation_action: str = "retry",  # "retry", "block", "alert"
        max_retries: int = 3,
        event_callback: callable | None = None,
    ):
        """Initialize GuardrailMiddleware.

        Args:
            enable_pii_detection: Whether to enable PII detection.
            enable_sensitive_detection: Whether to enable sensitive data detection.
            enable_schema_validation: Whether to enable JSON schema validation.
            pii_action: Action for PII violations: "mask", "block", or "alert".
            sensitive_action: Action for sensitive data: "mask", "block", or "alert".
            schema_validation_action: Action for schema violations: "retry", "block", or "alert".
            max_retries: Maximum retries for schema validation failures.
            event_callback: Optional callback for guardrail events.
        """
        super().__init__()
        self._enable_pii_detection = enable_pii_detection
        self._enable_sensitive_detection = enable_sensitive_detection
        self._enable_schema_validation = enable_schema_validation
        self._pii_action = pii_action
        self._sensitive_action = sensitive_action
        self._schema_validation_action = schema_validation_action
        self._max_retries = max_retries
        self._event_callback = event_callback
        self._retry_count = 0

    def _detect_pii(self, content: str) -> list[dict]:
        """Detect PII in content.

        Args:
            content: Text content to check.

        Returns:
            List of detected PII items with type and position.
        """
        if not self._enable_pii_detection:
            return []

        findings = []
        for pii_type, pattern in self.PII_PATTERNS.items():
            for match in pattern.finditer(content):
                findings.append({
                    "type": pii_type,
                    "start": match.start(),
                    "end": match.end(),
                    "value": match.group(),
                })

        return findings

    def _mask_pii(self, content: str, findings: list[dict]) -> str:
        """Mask detected PII in content.

        Args:
            content: Original content.
            findings: List of PII findings.

        Returns:
            Content with PII masked.
        """
        # Sort by position in reverse order to mask from end to start
        sorted_findings = sorted(findings, key=lambda x: x["start"], reverse=True)

        result = content
        for finding in sorted_findings:
            pii_type = finding["type"]
            start = finding["start"]
            end = finding["end"]
            mask = f"[{pii_type.upper()}_MASKED]"
            result = result[:start] + mask + result[end:]

        return result

    def _detect_sensitive(self, content: str) -> list[dict]:
        """Detect sensitive keywords in content.

        Args:
            content: Text content to check.

        Returns:
            List of detected sensitive items.
        """
        if not self._enable_sensitive_detection:
            return []

        findings = []
        content_lower = content.lower()

        for keyword in self.SENSITIVE_KEYWORDS:
            if keyword in content_lower:
                # Find all occurrences
                start = 0
                while True:
                    idx = content_lower.find(keyword, start)
                    if idx == -1:
                        break

                    # Extract surrounding context
                    context_start = max(0, idx - 20)
                    context_end = min(len(content), idx + len(keyword) + 20)
                    context = content[context_start:context_end]

                    findings.append({
                        "type": "sensitive_keyword",
                        "keyword": keyword,
                        "context": context,
                    })

                    start = idx + len(keyword)

        return findings

    def _validate_json_schema(
        self, content: str, expected_schema: dict | None
    ) -> tuple[bool, str]:
        """Validate JSON content against expected schema.

        Args:
            content: JSON string to validate.
            expected_schema: Expected JSON schema.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not self._enable_schema_validation or not expected_schema:
            return True, ""

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"

        # TODO: Implement JSON schema validation
        # For now, just check if it's valid JSON
        return True, ""

    def _emit_guardrail_event(
        self,
        violation_type: str,
        severity: str,
        details: dict,
    ) -> None:
        """Emit guardrail violation event.

        Args:
            violation_type: Type of violation.
            severity: Severity level (low, medium, high, critical).
            details: Additional details about the violation.
        """
        event = {
            "event_type": "guardrail_violation",
            "violation_type": violation_type,
            "severity": severity,
            "details": details,
            "timestamp": __import__("time").time(),
        }

        logger.warning(
            "GuardrailMiddleware: %s violation detected (severity: %s)",
            violation_type,
            severity,
        )

        if self._event_callback:
            try:
                self._event_callback(event)
            except Exception as e:
                logger.exception("Failed to emit guardrail event: %s", e)

    @override
    def after_model(self, state: WorkerState, runtime: Runtime, output) -> dict | None:
        """Apply guardrails to model output.

        This is called after model generation and acts on the final output
        before it's delivered to the user or tools.
        """
        if output is None:
            return None

        # Extract content from output
        content = ""
        if hasattr(output, "content"):
            content = output.content
        elif isinstance(output, str):
            content = output
        elif isinstance(output, dict):
            content = output.get("content", "")

        if not content:
            return None

        # Check for PII
        pii_findings = self._detect_pii(content)
        if pii_findings:
            self._emit_guardrail_event(
                "pii_detected",
                "high" if len(pii_findings) > 3 else "medium",
                {"count": len(pii_findings), "types": list(set(f["type"] for f in pii_findings))},
            )

            if self._pii_action == "mask":
                content = self._mask_pii(content, pii_findings)
                logger.info("GuardrailMiddleware: PII masked in output")
            elif self._pii_action == "block":
                logger.error("GuardrailMiddleware: PII detected, blocking output")
                raise ValueError("Output blocked due to PII detection")
            # "alert" just logs and continues

        # Check for sensitive data
        sensitive_findings = self._detect_sensitive(content)
        if sensitive_findings:
            self._emit_guardrail_event(
                "sensitive_data_detected",
                "medium",
                {"count": len(sensitive_findings)},
            )

            if self._sensitive_action == "block":
                logger.error(
                    "GuardrailMiddleware: Sensitive data detected, blocking output"
                )
                raise ValueError("Output blocked due to sensitive data detection")
            # "mask" and "alert" just log and continue for keywords

        # Validate JSON schema if applicable
        if content.strip().startswith(("{", "[")):
            schema = runtime.context.get("expected_schema") if runtime.context else None
            is_valid, error = self._validate_json_schema(content, schema)

            if not is_valid:
                self._emit_guardrail_event(
                    "schema_validation_failed",
                    "medium",
                    {"error": error},
                )

                if self._schema_validation_action == "retry":
                    self._retry_count += 1
                    if self._retry_count <= self._max_retries:
                        logger.warning(
                            "GuardrailMiddleware: Schema validation failed, retry %d/%d",
                            self._retry_count,
                            self._max_retries,
                        )
                        # Return instruction to retry
                        return {
                            "messages": [{
                                "role": "system",
                                "content": f"Previous output failed schema validation: {error}. Please regenerate with valid format.",
                            }]
                        }
                    else:
                        logger.error(
                            "GuardrailMiddleware: Max retries exceeded for schema validation"
                        )
                        raise ValueError(f"Schema validation failed after {self._max_retries} retries")
                elif self._schema_validation_action == "block":
                    raise ValueError(f"Schema validation failed: {error}")
                # "alert" just logs and continues

        # Update output if content was modified
        if content != (output.content if hasattr(output, "content") else output):
            if hasattr(output, "content"):
                output.content = content
            elif isinstance(output, str):
                output = content
            elif isinstance(output, dict):
                output["content"] = content

        return None
