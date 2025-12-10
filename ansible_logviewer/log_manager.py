"""
LogManager for Ansible log files.
Handles parsing, indexing, filtering, and rendering of log content.

Classes:
    LogEntry: Represents a single log line with metadata.
    LogSection: Represents a section of the log (header + body).
    LogManager: Manages the overall log, including parsing, filtering, and rendering.
"""

import re

class LogEntry:
    """Represents a single log line with parsed metadata."""
    def __init__(self, line: str, host: str | None = None,
                 status: str | None = None, task_name: str | None = None):
        self.line = line
        self.host = host
        self.status = status
        self.task_name = task_name

class LogSection:
    """
    Represents a section of the log, defined by a header and a body of log entries.
    Attributes:
        header (str | None): The header line of the section (e.g., TASK, PLAY).
        body (list of LogEntry | None): The list of LogEntry objects in this section.
        collapsed (bool): Whether the section is collapsed in the view.
        task_name (str | None): The name of the task associated with this section.

    Methods:
        __init__(header, body): Initializes the LogSection with header and body.
    """

    def __init__(self, header: str | None = None, body: list[LogEntry] | None = None):
        self.header = header
        self.body = body  # List of LogEntry objects
        self.collapsed = False
        self.task_name = None
        if header:
            # Extract task name from header
            match = re.search(r'(TASK|PLAY|PLAY RECAP|RUNNING HANDLER)\s*\[(.*?)\]', header)
            if match:
                self.task_name = match.group(2)

class LogManager:
    """
    Manages parsing, indexing, filtering, and rendering of Ansible log files.
    Provides methods to filter by host, task, and status, and to collapse/expand sections.

    Attributes:
        sections (list of LogSection): Parsed sections of the log.
        line_map (list): Maps rendered line indices to LogSection objects.
        entry_map (list): Maps rendered line indices to LogEntry objects (or None for headers).
        all_hosts (set): Set of all hosts found in the log.
        all_tasks (set): Set of all tasks found in the log.
        all_statuses (set): Set of all statuses found in the log.
        filter_hosts (set): Active host filters.
        filter_tasks (set): Active task filters.
        filter_statuses (set): Active status filters.

    Methods:
        get_host_stats(host): Returns statistics for a specific host.
        get_statuses_ordered(): Returns statuses in preferred order.
        set_filters(hosts, tasks, statuses): Sets active filters.
        clear_filters(): Clears all active filters.
        render(): Reconstructs the log text based on current filters and collapsed state.
        toggle_section(line_idx, collapse): Collapses or expands a section at the given line index.
        find_next_error(current_line_idx): Finds the next error line after the given index.
        find_previous_error(current_line_idx): Finds the previous error line before the given index.
        get_tasks_by_page(page_number, page_size): Retrieves a subset of tasks for pagination.
    """

    def __init__(self, content):
        """
        Initializes the LogManager by parsing the provided log content.
        Args:
            content (str): The full text content of the Ansible log file.
        """

        self.sections = []
        self.line_map = [] # Maps rendered line index to Section object
        self.entry_map = [] # Maps rendered line index to LogEntry (or None for headers)
        self.all_hosts = set()
        self.all_tasks = set()
        self.all_statuses = set()

        # Active filters (using sets for multi-select)
        self.filter_hosts = set()  # Changed from filter_host
        self.filter_tasks = set()  # Changed from filter_task
        self.filter_statuses = set()  # Changed from filter_status

        self._parse(content)
        self._index()
        self._index()

    def _parse_line(self, line: str, current_task: str) -> LogEntry:
        """
        Parse a line and extract host, status, and task information.

        Args:
            line (str): The log line to parse.
            current_task (str): The current task name for context.\

        Returns:
            LogEntry: Parsed log entry with metadata.
        """

        # Patterns for status detection
        re_ok = re.compile(r'^ok:\s*\[([^\]]+)\]')
        re_changed = re.compile(r'^changed:\s*\[([^\]]+)\]')
        re_failed = re.compile(r'^(fatal|FAILED)\s*[:-]\s*.*?\[([^\]]+)\]')
        re_unreachable = re.compile(r'^FAILED - UNREACHABLE!\s*\[([^\]]+)\]')
        re_skipping = re.compile(r'^skipping:\s*\[([^\]]+)\]')
        re_rescued = re.compile(r'^rescued:\s*\[([^\]]+)\]')
        re_recap = re.compile(r'^([a-zA-Z0-9\-._]+)\s*:\s*ok=')

        host = None
        status = None

        # Check for status patterns
        if re_unreachable.search(line):
            match = re_unreachable.search(line)
            host = match.group(1)
            status = 'unreachable'
        elif re_failed.search(line):
            match = re_failed.search(line)
            host = match.group(2) if match.lastindex >= 2 else None
            status = 'failed'
        elif re_rescued.search(line):
            match = re_rescued.search(line)
            host = match.group(1)
            status = 'rescued'
        elif re_ok.search(line):
            match = re_ok.search(line)
            host = match.group(1)
            status = 'ok'
        elif re_changed.search(line):
            match = re_changed.search(line)
            host = match.group(1)
            status = 'changed'
        elif re_skipping.search(line):
            match = re_skipping.search(line)
            host = match.group(1)
            status = 'skipping'
        elif re_recap.search(line):
            match = re_recap.search(line)
            host = match.group(1)
            status = 'recap'

        return LogEntry(line, host=host, status=status, task_name=current_task)

    def _parse(self, content: str):
        """
        Parses the log content into sections and entries.

        Splits the log into sections based on headers (TASK, PLAY, PLAY RECAP, RUNNING HANDLER).
        Each section contains a header line and a list of LogEntry objects representing the
        subsequent log lines until the next header.

        Args:
            content (str): The full text content of the Ansible log file.

        Note:
            - Lines before the first header are treated as a preamble section with header=None
            - Each LogEntry is parsed to extract host, status, and task metadata
            - Section headers are automatically parsed to extract task names for filtering
        """

        lines = content.splitlines()
        re_header = re.compile(r'(TASK|PLAY|PLAY RECAP|RUNNING HANDLER) \[.*\]')

        current_header = None
        current_body = []
        current_task = None

        for line in lines:
            # Check if line is a header
            is_header = re_header.search(line) or 'PLAY RECAP' in line

            if is_header:
                # Save previous section
                self.sections.append(LogSection(current_header, current_body))
                # Start new section
                current_header = line
                # Extract task name for filtering
                match = re.search(r'(TASK|PLAY|PLAY RECAP|RUNNING HANDLER)\s*\[(.*?)\]', line)
                current_task = match.group(2) if match else None
                current_body = []
            else:
                # Parse the line into a LogEntry
                entry = self._parse_line(line, current_task)
                current_body.append(entry)

        # Append final section
        self.sections.append(LogSection(current_header, current_body))

    def _index(self):
        """
        Build indexes of all hosts, tasks, and statuses.
        Populates self.all_hosts, self.all_tasks, and self.all_statuses sets.
        """

        for section in self.sections:
            if section.task_name:
                self.all_tasks.add(section.task_name)

            for entry in section.body:
                if entry.host:
                    self.all_hosts.add(entry.host)
                if entry.status:
                    self.all_statuses.add(entry.status)

    def get_host_stats(self, host: str) -> dict:
        """
        Get statistics for a specific host.

        Args:
            host (str): The hostname to get statistics for.

        Returns:
            dict: A dictionary with counts for total, ok,
                changed, failed, unreachable, skipping, rescued.
        """

        stats = {
            'total': 0,
            'ok': 0,
            'changed': 0,
            'failed': 0,
            'unreachable': 0,
            'skipping': 0,
            'rescued': 0
        }

        for section in self.sections:
            for entry in section.body:
                if entry.host == host:
                    stats['total'] += 1
                    if entry.status:
                        status_key = entry.status if entry.status != 'recap' else 'ok'
                        if status_key in stats:
                            stats[status_key] += 1

        return stats

    def get_statuses_ordered(self) -> list:
        """
        Get statuses in preferred order: ok, changed, unreachable, failed, skipping.
        Returns all standard statuses even if not present in the log.

        Returns:
            list: Ordered list of statuses.
        """

        # Always return these in this order
        return ['ok', 'changed', 'unreachable', 'failed', 'skipping']

    def set_filters(self, hosts: list[str] | None = None,
                    tasks: list[str] | None = None, statuses: list[str] | None = None):
        """
        Set active filters. Empty set or None means no filter for that category.
        Args:
            hosts (list or None): List of hostnames to filter by.
            tasks (list or None): List of task names to filter by.
            statuses (list or None): List of statuses to filter by.
        """

        self.filter_hosts = set(hosts) if hosts else set()
        self.filter_tasks = set(tasks) if tasks else set()
        self.filter_statuses = set(statuses) if statuses else set()

    def clear_filters(self):
        """
        Clear all active filters.
        """

        self.filter_hosts = set()
        self.filter_tasks = set()
        self.filter_statuses = set()

    def _matches_filters(self, entry, section) -> bool:
        """
        Check if an entry matches the current filters.

        Args:
            entry (LogEntry): The log entry to check.
            section (LogSection): The section containing the entry.

        Returns:
            bool: True if the entry matches all active filters, False otherwise.
        """

        # Check host filter (entry must match at least one selected host)
        if self.filter_hosts and entry.host not in self.filter_hosts:
            return False

        # Check status filter (entry must match at least one selected status)
        if self.filter_statuses and entry.status not in self.filter_statuses:
            return False

        # Check task filter (section must match at least one selected task)
        if self.filter_tasks and section.task_name not in self.filter_tasks:
            return False

        return True

    def render(self) -> str:
        """
        Reconstructs the full text based on collapsed state and filters.
        Populates self.line_map to map line indices to sections.

        Returns:
            str: The rendered log text.
        """

        rendered_lines = []
        self.line_map = []
        self.entry_map = []

        for section in self.sections:
            if section.header is None:
                # Preamble (no header) - always shown if no task filter
                if not self.filter_tasks:
                    for entry in section.body:
                        if self._matches_filters(entry, section):
                            rendered_lines.append(entry.line)
                            self.line_map.append(section)
                            self.entry_map.append(entry)
            else:
                # Check if section should be shown based on task filter
                if self.filter_tasks and section.task_name not in self.filter_tasks:
                    continue

                # Filter body lines
                filtered_body = [e for e in section.body if self._matches_filters(e, section)]

                # Only show section if it has matching entries
                if filtered_body or not (self.filter_hosts or self.filter_statuses):
                    # Header line
                    header_text = section.header
                    if section.collapsed:
                        header_text += " ..."

                    rendered_lines.append(header_text)
                    self.line_map.append(section)
                    self.entry_map.append(None)

                    # Body lines (only if not collapsed)
                    if not section.collapsed:
                        for entry in filtered_body:
                            rendered_lines.append(entry.line)
                            self.line_map.append(section)
                            self.entry_map.append(entry)

        return '\n'.join(rendered_lines)

    def toggle_section(self, line_idx: int = -1, collapse: bool = False) -> tuple[str, int] | int:
        """
        Collapses or expands the section at the given line index.
        Returns the new cursor line index (pointing to the section header).

        Args:
            line_idx (int): The line index in the rendered text.
            collapse (bool): True to collapse, False to expand.

        Returns:
            tuple: (new rendered text, new cursor line index)
        """

        if line_idx < 0 or line_idx >= len(self.line_map):
            return line_idx

        section = self.line_map[line_idx]
        if section.header is None:
            return line_idx # Cannot collapse preamble

        section.collapsed = collapse

        # Re-render to update line_map and text
        new_text = self.render()

        # Find the new position of this section (its header)
        try:
            new_cursor_idx = self.line_map.index(section)
        except ValueError:
            new_cursor_idx = 0

        return new_text, new_cursor_idx

    def find_next_error(self, current_line_idx: int) -> int | None:
        """
        Find the next rendered line with status failed or unreachable, or containing 'fatal'.
        Returns the line index, or None if not found.

        Args:
            current_line_idx (int): The current line index to start searching from.

        Returns:
            int | None: The line index of the next error, or None if not found.
        """

        fatal_pattern = re.compile(r'\bfatal\b', re.IGNORECASE)
        for idx in range(current_line_idx + 1, len(self.entry_map)):
            entry = self.entry_map[idx]
            if entry:
                if entry.status in ('failed', 'unreachable'):
                    return idx
                if fatal_pattern.search(entry.line):
                    return idx
        return None

    def find_previous_error(self, current_line_idx: int) -> int | None:
        """
        Find the previous rendered line with status failed or unreachable, or containing 'fatal'.
        Returns the line index, or None if not found.

        Args:
            current_line_idx (int): The current line index to start searching from.
        Returns:
            int | None: The line index of the previous error, or None if not found.
        """

        fatal_pattern = re.compile(r'\bfatal\b', re.IGNORECASE)
        for idx in range(current_line_idx - 1, -1, -1):
            entry = self.entry_map[idx]
            if entry:
                if entry.status in ('failed', 'unreachable'):
                    return idx
                if fatal_pattern.search(entry.line):
                    return idx
        return None

    def get_tasks_by_page(self, page_number: int, page_size: int) -> tuple[list[str], int]:
        """
        Retrieve a subset of tasks for the given page.

        Args:
            page_number (int): The page number to retrieve.
            page_size (int): The number of tasks per page.

        Returns:
            tuple: A tuple containing the list of tasks for the page and the total number of pages.
        """

        tasks = list(self.all_tasks)
        tasks.sort()  # Optional: Sort tasks alphabetically
        total_tasks = len(tasks)
        total_pages = (total_tasks + page_size - 1) // page_size

        if page_number < 1 or page_number > total_pages:
            return [], total_pages  # Return empty list if page is out of range

        start_index = (page_number - 1) * page_size
        end_index = min(start_index + page_size, total_tasks)
        return tasks[start_index:end_index], total_pages
