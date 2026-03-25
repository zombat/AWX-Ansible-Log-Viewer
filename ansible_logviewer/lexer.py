"""Syntax highlighting rules for Ansible log output."""

from __future__ import annotations

import re
from typing import Callable

from prompt_toolkit.document import Document
from prompt_toolkit.lexers import Lexer

TokenLine = list[tuple[str, str]]


class AnsibleLogLexer(Lexer):
    """Apply token styles to Ansible task, status, and recap lines."""

    def __init__(self) -> None:
        """Compile the regexes used during line classification."""
        super().__init__()
        self.header_pattern = re.compile(r"(TASK|PLAY|PLAY RECAP|RUNNING HANDLER) \[.*\]")
        self.fatal_pattern = re.compile(r"\b(fatal|failed):|\bFAILED\b|\bUNREACHABLE\b")
        self.error_pattern = re.compile(r"\b(ERROR|CRITICAL|Traceback)\b")
        self.changed_pattern = re.compile(r"\b(changed):")
        self.ok_pattern = re.compile(r"\b(ok):")
        self.skip_pattern = re.compile(r"\b(skipping):")
        self.rescued_pattern = re.compile(r"\b(rescued):")
        self.recap_failed_pattern = re.compile(r"failed=\d+")
        self.recap_unreachable_pattern = re.compile(r"unreachable=\d+")
        self.stats_line_pattern = re.compile(r"\s+:\s+ok=\d+")
        self.hostname_pattern = re.compile(r"^(\S+\s*:\s+)")
        self.stat_value_pattern = re.compile(r"(\w+)=(\d+)")

    def lex_document(self, document: Document) -> Callable[[int], TokenLine]:
        """Return a tokenizer callable for the current prompt_toolkit document."""

        def get_line_tokens(lineno: int) -> TokenLine:
            """Classify one line and return style-token pairs."""
            line = document.lines[lineno]
            if "PLAY RECAP" not in line and self.stats_line_pattern.search(line):
                return self._tokenize_stats_line(line)
            return [(self._classify_line(line), line)]

        return get_line_tokens

    def _tokenize_stats_line(self, line: str) -> TokenLine:
        """Tokenize recap statistic lines so non-zero failures stand out."""
        tokens: TokenLine = []
        hostname_match = self.hostname_pattern.match(line)
        if not hostname_match:
            return [("class:log.normal", line)]

        tokens.append(("class:log.normal", hostname_match.group(1)))
        rest = line[len(hostname_match.group(1)) :]
        position = 0

        # Preserve original spacing so the rendered line is unchanged apart from styling.
        for stat_name, stat_value in self.stat_value_pattern.findall(rest):
            pattern = f"{stat_name}={stat_value}"
            index = rest.find(pattern, position)
            if index > position:
                tokens.append(("class:log.normal", rest[position:index]))

            tokens.append((self._style_for_stat(stat_name, int(stat_value)), pattern))
            position = index + len(pattern)

        if position < len(rest):
            tokens.append(("class:log.normal", rest[position:]))
        return tokens

    def _style_for_stat(self, stat_name: str, value: int) -> str:
        """Return the display style for a recap statistic field."""
        if stat_name == "ok":
            return "class:log.success"
        if stat_name in {"changed", "rescued"}:
            return "class:log.changed" if value > 0 else "class:log.normal"
        if stat_name in {"failed", "unreachable"}:
            return "class:log.error" if value > 0 else "class:log.normal"
        if stat_name == "skipped":
            return "class:log.skip"
        return "class:log.normal"

    def _classify_line(self, line: str) -> str:
        """Return the dominant style class for a non-statistics line."""
        if "RUNNING HANDLER" in line:
            return "class:log.handler"
        if self.header_pattern.search(line):
            return "class:log.header"
        if self.fatal_pattern.search(line) or self.error_pattern.search(line):
            return "class:log.error"
        if self.changed_pattern.search(line) or self.rescued_pattern.search(line):
            return "class:log.changed"
        if self.ok_pattern.search(line):
            return "class:log.success"
        if self.skip_pattern.search(line):
            return "class:log.skip"
        if "PLAY RECAP" in line:
            return "class:log.header"
        if (
            self.recap_failed_pattern.search(line)
            and "failed=0" not in line
            or self.recap_unreachable_pattern.search(line)
            and "unreachable=0" not in line
        ):
            return "class:log.error"
        return "class:log.normal"
