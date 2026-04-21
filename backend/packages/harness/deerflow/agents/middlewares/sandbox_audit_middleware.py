"""SandboxAuditMiddleware - bash command security auditing with observability.

Enhanced with detailed observability:
- Command execution timing and resource tracking
- Dangerous command detection with metrics
- Structured audit records in WorkerState
"""

import json
import logging
import re
import shlex
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.agents.thread_state import ThreadState
from deerflow.agents.worker_state import WorkerState
from deerflow.observability.metrics import MetricsCollector
from deerflow.observability.pipeline import ObservabilityEvent, emit_event
from deerflow.observability.tracing import get_current_trace_context
from deerflow.observability.types import CommandAuditRecord, ObservabilityEventType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Command classification rules
# ---------------------------------------------------------------------------

# Each pattern is compiled once at import time.
_HIGH_RISK_PATTERNS: list[re.Pattern[str]] = [
    # --- original rules (retained) ---
    re.compile(r"rm\s+-[^\s]*r[^\s]*\s+(/\*?|~/?\*?|/home\b|/root\b)\s*$"),
    re.compile(r"dd\s+if="),
    re.compile(r"mkfs"),
    re.compile(r"cat\s+/etc/shadow"),
    re.compile(r">+\s*/etc/"),
    # --- pipe to sh/bash (generalised, replaces old curl|sh rule) ---
    re.compile(r"\|\s*(ba)?sh\b"),
    # --- command substitution (targeted – only dangerous executables) ---
    re.compile(r"[`$]\(?\s*(curl|wget|bash|sh|python|ruby|perl|base64)"),
    # --- base64 decode piped to execution ---
    re.compile(r"base64\s+.*-d.*\|"),
    # --- overwrite system binaries ---
    re.compile(r">+\s*(/usr/bin/|/bin/|/sbin/)"),
    # --- overwrite shell startup files ---
    re.compile(r">+\s*~/?\.(bashrc|profile|zshrc|bash_profile)"),
    # --- process environment leakage ---
    re.compile(r"/proc/[^/]+/environ"),
    # --- dynamic linker hijack (one-step escalation) ---
    re.compile(r"\b(LD_PRELOAD|LD_LIBRARY_PATH)\s*="),
    # --- bash built-in networking (bypasses tool allowlists) ---
    re.compile(r"/dev/tcp/"),
    # --- fork bomb ---
    re.compile(r"\S+\(\)\s*\{[^}]*\|\s*\S+\s*&"),  # :(){ :|:& };:
    re.compile(r"while\s+true.*&\s*done"),  # while true; do bash & done
]

_MEDIUM_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"chmod\s+777"),
    re.compile(r"pip3?\s+install"),
    re.compile(r"apt(-get)?\s+install"),
    # sudo/su: no-op under Docker root; warn so LLM is aware
    re.compile(r"\b(sudo|su)\b"),
    # PATH modification: long attack chain, warn rather than block
    re.compile(r"\bPATH\s*="),
]


def _split_compound_command(command: str) -> list[str]:
    """Split a compound command into sub-commands (quote-aware).

    Scans the raw command string so unquoted shell control operators are
    recognised even when they are not surrounded by whitespace
    (e.g. ``safe;rm -rf /`` or ``rm -rf /&&echo ok``). Operators inside
    quotes are ignored. If the command ends with an unclosed quote or a
    dangling escape, return the whole command unchanged (fail-closed —
    safer to classify the unsplit string than silently drop parts).
    """
    parts: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    escaping = False
    index = 0

    while index < len(command):
        char = command[index]

        if escaping:
            current.append(char)
            escaping = False
            index += 1
            continue

        if char == "\\" and not in_single_quote:
            current.append(char)
            escaping = True
            index += 1
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
            index += 1
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
            index += 1
            continue

        if not in_single_quote and not in_double_quote:
            if command.startswith("&&", index) or command.startswith("||", index):
                part = "".join(current).strip()
                if part:
                    parts.append(part)
                current = []
                index += 2
                continue
            if char == ";":
                part = "".join(current).strip()
                if part:
                    parts.append(part)
                current = []
                index += 1
                continue

        current.append(char)
        index += 1

    # Unclosed quote or dangling escape → fail-closed, return whole command
    if in_single_quote or in_double_quote or escaping:
        return [command]

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts if parts else [command]


def _classify_single_command(command: str) -> str:
    """Classify a single (non-compound) command. Return 'block', 'warn', or 'pass'."""
    normalized = " ".join(command.split())

    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(normalized):
            return "block"

    # Also try shlex-parsed tokens for high-risk detection
    try:
        tokens = shlex.split(command)
        joined = " ".join(tokens)
        for pattern in _HIGH_RISK_PATTERNS:
            if pattern.search(joined):
                return "block"
    except ValueError:
        # shlex.split fails on unclosed quotes — treat as suspicious
        return "block"

    for pattern in _MEDIUM_RISK_PATTERNS:
        if pattern.search(normalized):
            return "warn"

    return "pass"


def _classify_command(command: str) -> str:
    """Return 'block', 'warn', or 'pass'.

    Strategy:
    1. First scan the *whole* raw command against high-risk patterns. This
       catches structural attacks like ``while true; do bash & done`` or
       ``:(){ :|:& };:`` that span multiple shell statements — splitting them
       on ``;`` would destroy the pattern context.
    2. Then split compound commands (e.g. ``cmd1 && cmd2 ; cmd3``) and
       classify each sub-command independently. The most severe verdict wins.
    """
    # Pass 1: whole-command high-risk scan (catches multi-statement patterns)
    normalized = " ".join(command.split())
    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(normalized):
            return "block"

    # Pass 2: per-sub-command classification
    sub_commands = _split_compound_command(command)
    worst = "pass"
    for sub in sub_commands:
        verdict = _classify_single_command(sub)
        if verdict == "block":
            return "block"  # short-circuit: can't get worse
        if verdict == "warn":
            worst = "warn"
    return worst


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class SandboxAuditMiddleware(AgentMiddleware[ThreadState]):
    """Bash command security auditing middleware with observability.

    For every ``bash`` tool call:
    1. **Command classification**: regex + shlex analysis grades commands as
       high-risk (block), medium-risk (warn), or safe (pass).
    2. **Audit log**: every bash call is recorded as a structured JSON entry
       via the standard logger (visible in langgraph.log).
    3. **Observability**: detailed timing, resource usage, and dangerous
       command detection with metrics.

    High-risk commands (e.g. ``rm -rf /``, ``curl url | bash``) are blocked:
    the handler is not called and an error ``ToolMessage`` is returned so the
    agent loop can continue gracefully.

    Medium-risk commands (e.g. ``pip install``, ``chmod 777``) are executed
    normally; a warning is appended to the tool result so the LLM is aware.
    """

    state_schema = ThreadState

    # Dangerous command flag types for metrics
    DANGER_FLAG_TYPES = {
        r"rm\s+-[^\s]*r[^\s]*\s+(/\*?|~/?\*?|/home\b|/root\b)\s*$": "dangerous_delete",
        r"dd\s+if=": "disk_operation",
        r"mkfs": "disk_operation",
        r"\|\s*(ba)?sh\b": "pipe_to_shell",
        r"[`$]\(?\s*(curl|wget|bash|sh|python|ruby|perl|base64)": "command_substitution",
        r"base64\s+.*-d.*\|": "base64_decode",
        r"\b(LD_PRELOAD|LD_LIBRARY_PATH)\s*=": "linker_hijack",
        r"/dev/tcp/": "bash_networking",
        r"\S+\(\)\s*\{[^}]*\|\s*\S+\s*&": "fork_bomb",
    }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_thread_id(self, request: ToolCallRequest) -> str | None:
        runtime = request.runtime  # ToolRuntime; may be None-like in tests
        if runtime is None:
            return None
        ctx = getattr(runtime, "context", None) or {}
        thread_id = ctx.get("thread_id") if isinstance(ctx, dict) else None
        if thread_id is None:
            cfg = getattr(runtime, "config", None) or {}
            thread_id = cfg.get("configurable", {}).get("thread_id")
        return thread_id

    _AUDIT_COMMAND_LIMIT = 200

    def _write_audit(self, thread_id: str | None, command: str, verdict: str, *, truncate: bool = False) -> None:
        audited_command = command
        if truncate and len(command) > self._AUDIT_COMMAND_LIMIT:
            audited_command = f"{command[: self._AUDIT_COMMAND_LIMIT]}... ({len(command)} chars)"
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "thread_id": thread_id or "unknown",
            "command": audited_command,
            "verdict": verdict,
        }
        logger.info("[SandboxAudit] %s", json.dumps(record, ensure_ascii=False))

    def _create_audit_record(self, command: str, verdict: str) -> CommandAuditRecord:
        """Create a command audit record for observability."""
        danger_flags = []
        if verdict == "block":
            for pattern_str, flag_type in self.DANGER_FLAG_TYPES.items():
                if re.search(pattern_str, command):
                    danger_flags.append(flag_type)

        return CommandAuditRecord(
            command_id=str(uuid.uuid4()),
            command=command[:1000] if len(command) > 1000 else command,
            start_time=time.time(),
            is_dangerous=verdict == "block",
            danger_flags=danger_flags,
        )

    def _emit_command_event(self, record: CommandAuditRecord, event_type: str) -> None:
        """Emit command execution observability event."""
        trace_ctx = get_current_trace_context()
        event = ObservabilityEvent(
            event_type=event_type,
            timestamp=record.end_time or time.time(),
            trace_id=trace_ctx.trace_id if trace_ctx else None,
            span_id=trace_ctx.span_id if trace_ctx else None,
            payload={
                "command_id": record.command_id,
                "command_preview": record.command[:200] if record.command else "",
                "sandbox_level": record.sandbox_level,
                "duration_ms": record.duration_ms,
                "exit_code": record.exit_code,
                "is_dangerous": record.is_dangerous,
                "danger_flags": record.danger_flags,
                "status": record.status,
            },
        )
        emit_event(event)

    def _record_command_metrics(self, record: CommandAuditRecord) -> None:
        """Record command execution metrics."""
        duration_sec = (record.duration_ms or 0) / 1000.0
        MetricsCollector.record_command_execution(
            sandbox_level=record.sandbox_level,
            duration_sec=duration_sec,
        )
        if record.is_dangerous:
            for flag in record.danger_flags:
                MetricsCollector.record_dangerous_command(flag_type=flag)

    def _build_block_message(self, request: ToolCallRequest, reason: str) -> ToolMessage:
        tool_call_id = str(request.tool_call.get("id") or "missing_id")
        return ToolMessage(
            content=f"Command blocked: {reason}. Please use a safer alternative approach.",
            tool_call_id=tool_call_id,
            name="bash",
            status="error",
        )

    def _append_warn_to_result(self, result: ToolMessage | Command, command: str) -> ToolMessage | Command:
        """Append a warning note to the tool result for medium-risk commands."""
        if not isinstance(result, ToolMessage):
            return result
        warning = f"\n\n⚠️ Warning: `{command}` is a medium-risk command that may modify the runtime environment."
        if isinstance(result.content, list):
            new_content = list(result.content) + [{"type": "text", "text": warning}]
        else:
            new_content = str(result.content) + warning
        return ToolMessage(
            content=new_content,
            tool_call_id=result.tool_call_id,
            name=result.name,
            status=result.status,
        )

    # ------------------------------------------------------------------
    # Input sanitisation
    # ------------------------------------------------------------------

    # Normal bash commands rarely exceed a few hundred characters.  10 000 is
    # well above any legitimate use case yet a tiny fraction of Linux ARG_MAX.
    # Anything longer is almost certainly a payload injection or base64-encoded
    # attack string.
    _MAX_COMMAND_LENGTH = 10_000

    def _validate_input(self, command: str) -> str | None:
        """Return ``None`` if *command* is acceptable, else a rejection reason."""
        if not command.strip():
            return "empty command"
        if len(command) > self._MAX_COMMAND_LENGTH:
            return "command too long"
        if "\x00" in command:
            return "null byte detected"
        return None

    # ------------------------------------------------------------------
    # Core logic (shared between sync and async paths)
    # ------------------------------------------------------------------

    def _pre_process(self, request: ToolCallRequest) -> tuple[str, str | None, str, str | None]:
        """
        Returns (command, thread_id, verdict, reject_reason).
        verdict is 'block', 'warn', or 'pass'.
        reject_reason is non-None only for input sanitisation rejections.
        """
        args = request.tool_call.get("args", {})
        raw_command = args.get("command")
        command = raw_command if isinstance(raw_command, str) else ""
        thread_id = self._get_thread_id(request)

        # ① input sanitisation — reject malformed input before regex analysis
        reject_reason = self._validate_input(command)
        if reject_reason:
            self._write_audit(thread_id, command, "block", truncate=True)
            logger.warning("[SandboxAudit] INVALID INPUT thread=%s reason=%s", thread_id, reject_reason)
            return command, thread_id, "block", reject_reason

        # ② classify command
        verdict = _classify_command(command)

        # ③ audit log
        self._write_audit(thread_id, command, verdict)

        if verdict == "block":
            logger.warning("[SandboxAudit] BLOCKED thread=%s cmd=%r", thread_id, command)
        elif verdict == "warn":
            logger.warning("[SandboxAudit] WARN (medium-risk) thread=%s cmd=%r", thread_id, command)

        return command, thread_id, verdict, None

    # ------------------------------------------------------------------
    # wrap_tool_call hooks
    # ------------------------------------------------------------------

    def _parse_result(self, record: CommandAuditRecord, result: ToolMessage | Command) -> None:
        """Parse tool result to extract execution info."""
        if isinstance(result, ToolMessage):
            content = result.content
            if isinstance(content, str):
                # Try to extract exit code from common patterns
                import re
                exit_match = re.search(r"exit\s*code[:\s]*(\d+)", content.lower())
                if exit_match:
                    record.exit_code = int(exit_match.group(1))
                else:
                    record.exit_code = 0 if not result.status or result.status != "error" else 1

                # Extract stdout/stderr preview
                lines = content.split("\n")
                record.stdout_preview = "\n".join(lines[:10])
            record.status = "success" if result.status != "error" else "error"
        else:
            record.status = "success"
            record.exit_code = 0

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if request.tool_call.get("name") != "bash":
            return handler(request)

        command, _, verdict, reject_reason = self._pre_process(request)

        # Create audit record for observability
        audit_record = self._create_audit_record(command, verdict)

        if verdict == "block":
            reason = reject_reason or "security violation detected"
            audit_record.status = "blocked"
            audit_record.end_time = time.time()
            audit_record.duration_ms = 0
            self._emit_command_event(audit_record, ObservabilityEventType.DANGEROUS_COMMAND_DETECTED)
            self._record_command_metrics(audit_record)
            return self._build_block_message(request, reason)

        try:
            result = handler(request)
            self._parse_result(audit_record, result)
        except Exception as exc:
            audit_record.status = "error"
            audit_record.error_message = str(exc)
            audit_record.exit_code = 1
            raise
        finally:
            audit_record.end_time = time.time()
            audit_record.duration_ms = int((audit_record.end_time - audit_record.start_time) * 1000)

            event_type = (
                ObservabilityEventType.COMMAND_EXECUTION_COMPLETED
                if audit_record.status in ("success", "blocked")
                else ObservabilityEventType.COMMAND_EXECUTION_FAILED
            )
            self._emit_command_event(audit_record, event_type)
            self._record_command_metrics(audit_record)

        if verdict == "warn":
            result = self._append_warn_to_result(result, command)
        return result

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if request.tool_call.get("name") != "bash":
            return await handler(request)

        command, _, verdict, reject_reason = self._pre_process(request)

        # Create audit record for observability
        audit_record = self._create_audit_record(command, verdict)

        if verdict == "block":
            reason = reject_reason or "security violation detected"
            audit_record.status = "blocked"
            audit_record.end_time = time.time()
            audit_record.duration_ms = 0
            self._emit_command_event(audit_record, ObservabilityEventType.DANGEROUS_COMMAND_DETECTED)
            self._record_command_metrics(audit_record)
            return self._build_block_message(request, reason)

        try:
            result = await handler(request)
            self._parse_result(audit_record, result)
        except Exception as exc:
            audit_record.status = "error"
            audit_record.error_message = str(exc)
            audit_record.exit_code = 1
            raise
        finally:
            audit_record.end_time = time.time()
            audit_record.duration_ms = int((audit_record.end_time - audit_record.start_time) * 1000)

            event_type = (
                ObservabilityEventType.COMMAND_EXECUTION_COMPLETED
                if audit_record.status in ("success", "blocked")
                else ObservabilityEventType.COMMAND_EXECUTION_FAILED
            )
            self._emit_command_event(audit_record, event_type)
            self._record_command_metrics(audit_record)

        if verdict == "warn":
            result = self._append_warn_to_result(result, command)
        return result
