"""Parser for OpenCode CLI JSON output."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class OpenCodeJSONParser(BaseParser):
    """Parse stdout produced by OpenCode CLI with JSON output."""

    name = "opencode_json"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        if not stdout.strip():
            raise ParserError("OpenCode CLI returned empty stdout while JSON output was expected")

        # OpenCode outputs JSONL (one JSON object per line) - parse each line
        lines = stdout.strip().split("\n")
        events: list[dict[str, Any]] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    events.append(event)
            except json.JSONDecodeError:
                # Skip non-JSON lines
                continue

        if not events:
            # Fallback: try parsing entire stdout as single JSON
            try:
                loaded = json.loads(stdout)
                if isinstance(loaded, dict):
                    events = [loaded]
                elif isinstance(loaded, list):
                    events = [e for e in loaded if isinstance(e, dict)]
            except json.JSONDecodeError as exc:
                raise ParserError(f"Failed to decode OpenCode CLI JSON output: {exc}") from exc

        metadata: dict[str, Any] = {"events": events}

        # Extract content from JSONL events
        content: str = ""

        # Look for "text" type events which contain the actual response
        for event in events:
            event_type = event.get("type")
            if event_type == "text":
                # Extract text from part.text
                part = event.get("part", {})
                text = part.get("text", "")
                if text:
                    # Remove <SUMMARY> blocks if present
                    if "<SUMMARY>" in text:
                        text = text.split("<SUMMARY>")[0].strip()
                    content = text
                    break
            elif not content:
                # Fallback to generic content extraction
                content = self._extract_content(event)

        # Build metadata from step_finish event if present
        for event in events:
            if event.get("type") == "step_finish":
                metadata.update(self._build_metadata(event))
                break

        stderr_text = stderr.strip()
        if stderr_text:
            metadata["stderr"] = stderr_text

        if content:
            return ParsedCLIResponse(content=content, metadata=metadata)

        # Fallback to stderr if no content found
        if stderr_text:
            return ParsedCLIResponse(
                content="OpenCode CLI returned no textual result. Raw stderr was preserved for troubleshooting.",
                metadata=metadata,
            )

        raise ParserError("OpenCode CLI response did not contain a textual result")

    def _extract_content(self, payload: dict[str, Any]) -> str:
        """Extract textual content from OpenCode response."""
        # Try various common response fields
        for key in ("content", "result", "message", "response", "text", "output"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                # Join list of strings
                joined = [part.strip() for part in value if isinstance(part, str) and part.strip()]
                if joined:
                    return "\n".join(joined)

        # Check for nested content in 'data' field
        data = payload.get("data")
        if isinstance(data, dict):
            return self._extract_content(data)

        return ""

    def _build_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract metadata from OpenCode response."""
        metadata: dict[str, Any] = {}

        # Common metadata fields
        if "model" in payload:
            metadata["model_used"] = payload["model"]
        if "usage" in payload and isinstance(payload["usage"], dict):
            metadata["usage"] = payload["usage"]
        if "thinking" in payload:
            metadata["thinking"] = payload["thinking"]
        if "error" in payload:
            metadata["is_error"] = True
            error = payload["error"]
            if isinstance(error, dict):
                metadata["error_message"] = error.get("message", str(error))
            else:
                metadata["error_message"] = str(error)
        if "duration" in payload:
            metadata["duration_ms"] = payload["duration"]
        if "session_id" in payload:
            metadata["session_id"] = payload["session_id"]

        return metadata
