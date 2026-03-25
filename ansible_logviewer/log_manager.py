"""Log parsing and filtering primitives for the Ansible log viewer."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Pattern


HEADER_PATTERN = re.compile(r"(TASK|PLAY|PLAY RECAP|RUNNING HANDLER)\s*\[(.*?)\]")
RECAP_HEADER_PATTERN = re.compile(r"^PLAY RECAP")


@dataclass(slots=True)
class LogEntry:
    """Represent a single rendered log line and its parsed metadata."""

    line: str
    host: str | None = None
    status: str | None = None
    task_name: str | None = None


@dataclass(slots=True)
class LogSection:
    """Represent a logical log section with a header and related entries."""

    header: str | None = None
    body: list[LogEntry] = field(default_factory=list)
    collapsed: bool = False
    task_name: str | None = None

    def __post_init__(self) -> None:
        """Populate the task name from the section header when available."""
        if self.header:
            match = HEADER_PATTERN.search(self.header)
            if match:
                self.task_name = match.group(2)


class LogManager:
    """Parse, filter, render, and navigate Ansible log content."""

    _status_patterns: dict[str, Pattern[str]] = {
        "unreachable": re.compile(r"^fatal:\s*\[([^\]]+)\]:\s*UNREACHABLE!"),
        "failed": re.compile(r"^(?:fatal|FAILED)[: ].*?\[([^\]]+)\]"),
        "rescued": re.compile(r"^rescued:\s*\[([^\]]+)\]"),
        "ok": re.compile(r"^ok:\s*\[([^\]]+)\]"),
        "changed": re.compile(r"^changed:\s*\[([^\]]+)\]"),
        "skipping": re.compile(r"^skipping:\s*\[([^\]]+)\]"),
        "recap": re.compile(r"^([a-zA-Z0-9._-]+)\s*:\s*ok="),
    }

    def __init__(self, content: str) -> None:
        """Initialize the manager from raw log content."""
        self.sections: list[LogSection] = []
        self.line_map: list[LogSection] = []
        self.entry_map: list[LogEntry | None] = []
        self.all_hosts: set[str] = set()
        self.all_tasks: set[str] = set()
        self.all_statuses: set[str] = set()
        self.filter_hosts: set[str] = set()
        self.filter_tasks: set[str] = set()
        self.filter_statuses: set[str] = set()

        self._parse(content)
        self._index()

    def _parse_line(self, line: str, current_task: str | None) -> LogEntry:
        """Extract host and status metadata from a single log line."""
        stripped_line = line.strip()
        host: str | None = None
        status: str | None = None

        # The first matching pattern wins because Ansible status prefixes are mutually exclusive.
        for status_name, pattern in self._status_patterns.items():
            match = pattern.search(stripped_line)
            if match:
                host = match.group(1)
                status = status_name
                break

        return LogEntry(line=line, host=host, status=status, task_name=current_task)

    def _parse(self, content: str) -> None:
        """Split the log into sections keyed by task, play, and recap headers."""
        current_header: str | None = None
        current_body: list[LogEntry] = []
        current_task: str | None = None

        for line in content.splitlines():
            if not line.strip() and current_header is None and not current_body:
                continue

            is_header = bool(HEADER_PATTERN.search(line) or RECAP_HEADER_PATTERN.search(line))

            if is_header:
                if current_header is not None or current_body:
                    self.sections.append(LogSection(header=current_header, body=current_body))

                current_header = line
                current_body = []
                match = HEADER_PATTERN.search(line)
                current_task = match.group(2) if match else None
                continue

            current_body.append(self._parse_line(line, current_task))

        if current_header is not None or current_body:
            self.sections.append(LogSection(header=current_header, body=current_body))

    def _index(self) -> None:
        """Build lookup sets for filters and status summaries."""
        for section in self.sections:
            if section.task_name:
                self.all_tasks.add(section.task_name)

            for entry in section.body:
                if entry.host:
                    self.all_hosts.add(entry.host)
                if entry.status:
                    self.all_statuses.add(entry.status)

    def get_host_stats(self, host: str) -> dict[str, int]:
        """Return aggregated status counters for a host."""
        stats = {
            "total": 0,
            "ok": 0,
            "changed": 0,
            "failed": 0,
            "unreachable": 0,
            "skipping": 0,
            "rescued": 0,
        }

        for section in self.sections:
            for entry in section.body:
                if entry.host != host:
                    continue

                stats["total"] += 1
                status_key = "ok" if entry.status == "recap" else entry.status
                if status_key and status_key in stats:
                    stats[status_key] += 1

        return stats

    def get_statuses_ordered(self) -> list[str]:
        """Return statuses in a stable order for the filter dialog."""
        return ["ok", "changed", "unreachable", "failed", "skipping", "rescued"]

    def set_filters(
        self,
        hosts: set[str] | list[str] | None = None,
        tasks: set[str] | list[str] | None = None,
        statuses: set[str] | list[str] | None = None,
    ) -> None:
        """Store the active host, task, and status filters."""
        self.filter_hosts = set(hosts) if hosts else set()
        self.filter_tasks = set(tasks) if tasks else set()
        self.filter_statuses = set(statuses) if statuses else set()

    def clear_filters(self) -> None:
        """Remove all active filters."""
        self.filter_hosts.clear()
        self.filter_tasks.clear()
        self.filter_statuses.clear()

    def _matches_filters(self, entry: LogEntry, section: LogSection) -> bool:
        """Return whether an entry survives the current filter state."""
        if self.filter_hosts and entry.host not in self.filter_hosts:
            return False
        if self.filter_statuses and entry.status not in self.filter_statuses:
            return False
        if self.filter_tasks and section.task_name not in self.filter_tasks:
            return False
        return True

    def render(self) -> str:
        """Render the current filtered view and rebuild line indexes."""
        rendered_lines: list[str] = []
        self.line_map = []
        self.entry_map = []

        for section in self.sections:
            if section.header is None:
                if self.filter_tasks:
                    continue

                for entry in section.body:
                    if self._matches_filters(entry, section):
                        rendered_lines.append(entry.line)
                        self.line_map.append(section)
                        self.entry_map.append(entry)
                continue

            if self.filter_tasks and section.task_name not in self.filter_tasks:
                continue

            filtered_body = [entry for entry in section.body if self._matches_filters(entry, section)]

            # Keep headers visible if the section itself is selected and no line-level filter removed it.
            if not filtered_body and (self.filter_hosts or self.filter_statuses):
                continue

            header_text = f"{section.header} ..." if section.collapsed else section.header
            rendered_lines.append(header_text)
            self.line_map.append(section)
            self.entry_map.append(None)

            if section.collapsed:
                continue

            for entry in filtered_body:
                rendered_lines.append(entry.line)
                self.line_map.append(section)
                self.entry_map.append(entry)

        return "\n".join(rendered_lines)

    def toggle_section(self, line_idx: int = -1, collapse: bool = False) -> tuple[str, int] | int:
        """Collapse or expand the section referenced by a rendered line index."""
        if line_idx < 0 or line_idx >= len(self.line_map):
            return line_idx

        section = self.line_map[line_idx]
        if section.header is None:
            return line_idx

        section.collapsed = collapse
        new_text = self.render()

        try:
            new_cursor_idx = self.line_map.index(section)
        except ValueError:
            new_cursor_idx = 0

        return new_text, new_cursor_idx

    def _is_error_entry(self, entry: LogEntry | None) -> bool:
        """Return whether an entry should be treated as an error navigation target."""
        if entry is None:
            return False
        if entry.status in {"failed", "unreachable"}:
            return True
        return bool(re.search(r"\bfatal\b", entry.line, re.IGNORECASE))

    def find_next_error(self, current_line_idx: int) -> int | None:
        """Return the next rendered line index that contains an error."""
        if not self.entry_map:
            self.render()
        for index in range(current_line_idx + 1, len(self.entry_map)):
            if self._is_error_entry(self.entry_map[index]):
                return index
        return None

    def find_previous_error(self, current_line_idx: int) -> int | None:
        """Return the previous rendered line index that contains an error."""
        if not self.entry_map:
            self.render()
        for index in range(current_line_idx - 1, -1, -1):
            if self._is_error_entry(self.entry_map[index]):
                return index
        return None

    def get_tasks_by_page(self, page_number: int, page_size: int) -> tuple[list[str], int]:
        """Return a slice of task names and the total number of pages."""
        tasks = sorted(self.all_tasks)
        total_tasks = len(tasks)
        if page_size <= 0:
            return [], 0

        total_pages = (total_tasks + page_size - 1) // page_size
        if page_number < 1 or page_number > total_pages:
            return [], total_pages

        start_index = (page_number - 1) * page_size
        end_index = min(start_index + page_size, total_tasks)
        return tasks[start_index:end_index], total_pages
