import re
import logging

class LogEntry:
    """Represents a single log line with parsed metadata."""
    def __init__(self, line, host=None, status=None, task_name=None):
        self.line = line
        self.host = host
        self.status = status
        self.task_name = task_name

class LogSection:
    def __init__(self, header, body):
        self.header = header
        self.body = body  # List of LogEntry objects
        self.collapsed = False
        self.task_name = None
        if header:
            # Extract task name from header
            match = re.search(r'(TASK|PLAY|PLAY RECAP)\s*\[(.*?)\]', header)
            if match:
                self.task_name = match.group(2)

class LogManager:
    def __init__(self, content):
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
        
    def _parse_line(self, line, current_task):
        """Parse a line and extract host, status, and task information."""
        # Patterns for status detection
        re_ok = re.compile(r'^ok:\s*\[([^\]]+)\]')
        re_changed = re.compile(r'^changed:\s*\[([^\]]+)\]')
        re_failed = re.compile(r'^(fatal|FAILED)\s*[:-]\s*.*?\[([^\]]+)\]')
        re_unreachable = re.compile(r'^FAILED - UNREACHABLE!\s*\[([^\]]+)\]')
        re_skipping = re.compile(r'^skipping:\s*\[([^\]]+)\]')
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
        
    def _parse(self, content):
        lines = content.splitlines()
        re_header = re.compile(r'(TASK|PLAY|PLAY RECAP) \[.*\]')
        
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
                match = re.search(r'(TASK|PLAY|PLAY RECAP)\s*\[(.*?)\]', line)
                current_task = match.group(2) if match else None
                current_body = []
            else:
                # Parse the line into a LogEntry
                entry = self._parse_line(line, current_task)
                current_body.append(entry)
                
        # Append final section
        self.sections.append(LogSection(current_header, current_body))

    def _index(self):
        """Build indexes of all hosts, tasks, and statuses."""
        for section in self.sections:
            if section.task_name:
                self.all_tasks.add(section.task_name)
            
            for entry in section.body:
                if entry.host:
                    self.all_hosts.add(entry.host)
                if entry.status:
                    self.all_statuses.add(entry.status)
    
    def get_host_stats(self, host):
        """Get statistics for a specific host."""
        stats = {
            'total': 0,
            'ok': 0,
            'changed': 0,
            'failed': 0,
            'unreachable': 0,
            'skipping': 0
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
    
    def get_statuses_ordered(self):
        """Get statuses in preferred order: ok, changed, unreachable, failed, skipping.
        Returns all standard statuses even if not present in the log."""
        # Always return these in this order
        return ['ok', 'changed', 'unreachable', 'failed', 'skipping']
    
    def set_filters(self, hosts=None, tasks=None, statuses=None):
        """Set active filters. Empty set or None means no filter for that category."""
        self.filter_hosts = set(hosts) if hosts else set()
        self.filter_tasks = set(tasks) if tasks else set()
        self.filter_statuses = set(statuses) if statuses else set()
    
    def clear_filters(self):
        """Clear all active filters."""
        self.filter_hosts = set()
        self.filter_tasks = set()
        self.filter_statuses = set()
    
    def _matches_filters(self, entry, section):
        """Check if an entry matches the current filters."""
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

    def render(self):
        """
        Reconstructs the full text based on collapsed state and filters.
        Populates self.line_map to map line indices to sections.
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

    def toggle_section(self, line_idx, collapse):
        """
        Collapses or expands the section at the given line index.
        Returns the new cursor line index (pointing to the section header).
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

    def find_next_error(self, current_line_idx):
        """Find the next rendered line with status failed or unreachable, or containing 'fatal'.
        Returns the line index, or None if not found."""
        import re
        fatal_pattern = re.compile(r'\bfatal\b', re.IGNORECASE)
        for idx in range(current_line_idx + 1, len(self.entry_map)):
            entry = self.entry_map[idx]
            if entry:
                if entry.status in ('failed', 'unreachable'):
                    return idx
                if fatal_pattern.search(entry.line):
                    return idx
        return None

    def find_previous_error(self, current_line_idx):
        """Find the previous rendered line with status failed or unreachable, or containing 'fatal'.
        Returns the line index, or None if not found."""
        import re
        fatal_pattern = re.compile(r'\bfatal\b', re.IGNORECASE)
        for idx in range(current_line_idx - 1, -1, -1):
            entry = self.entry_map[idx]
            if entry:
                if entry.status in ('failed', 'unreachable'):
                    return idx
                if fatal_pattern.search(entry.line):
                    return idx
        return None

    def get_tasks_by_page(self, page_number, page_size):
        """Retrieve a subset of tasks for the given page."""
        tasks = list(self.all_tasks)
        tasks.sort()  # Optional: Sort tasks alphabetically
        total_tasks = len(tasks)
        total_pages = (total_tasks + page_size - 1) // page_size

        if page_number < 1 or page_number > total_pages:
            return [], total_pages  # Return empty list if page is out of range

        start_index = (page_number - 1) * page_size
        end_index = min(start_index + page_size, total_tasks)
        return tasks[start_index:end_index], total_pages
