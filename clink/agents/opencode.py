"""OpenCode-specific CLI agent hooks."""

from __future__ import annotations

import json
from typing import Any

from clink.models import ResolvedCLIClient
from clink.parsers.base import ParsedCLIResponse

from .base import AgentOutput, BaseCLIAgent


class OpenCodeAgent(BaseCLIAgent):
    """OpenCode-specific behaviour."""

    def __init__(self, client: ResolvedCLIClient):
        super().__init__(client)

    def _recover_from_error(
        self,
        *,
        returncode: int,
        stdout: str,
        stderr: str,
        sanitized_command: list[str],
        duration_seconds: float,
        output_file_content: str | None,
    ) -> AgentOutput | None:
        """Attempt to recover from OpenCode CLI errors."""
        combined = "\n".join(part for part in (stderr, stdout) if part)
        if not combined:
            return None

        # Try to extract JSON error payload
        brace_index = combined.find("{")
        if brace_index == -1:
            return None

        json_candidate = combined[brace_index:]
        try:
            payload: dict[str, Any] = json.loads(json_candidate)
        except json.JSONDecodeError:
            return None

        # Extract error information
        error_block = payload.get("error")
        if not isinstance(error_block, dict):
            # Maybe the whole payload is an error
            if "message" in payload or "error" in payload:
                error_block = payload
            else:
                return None

        code = error_block.get("code") if isinstance(error_block, dict) else None
        err_type = error_block.get("type") if isinstance(error_block, dict) else None
        detail_message = (
            error_block.get("message")
            if isinstance(error_block, dict)
            else str(error_block)
        )

        # Build error message
        prologue = combined[:brace_index].strip()
        lines: list[str] = []
        if prologue and (not detail_message or prologue not in detail_message):
            lines.append(prologue)
        if detail_message:
            lines.append(detail_message)

        header = "OpenCode CLI reported an error"
        if code:
            header = f"{header} ({code})"
        elif err_type:
            header = f"{header} ({err_type})"

        content_lines = [header.rstrip(".") + "."]
        content_lines.extend(lines)
        message = "\n".join(content_lines).strip()

        metadata = {
            "cli_error_recovered": True,
            "cli_error_code": code,
            "cli_error_type": err_type,
            "cli_error_payload": payload,
        }

        parsed = ParsedCLIResponse(content=message or header, metadata=metadata)
        return AgentOutput(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            parser_name=self._parser.name,
            output_file_content=output_file_content,
        )
