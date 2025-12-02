import re
import logging

class LogSection:
    def __init__(self, header, body):
        self.header = header
        self.body = body
        self.collapsed = False

class LogManager:
    def __init__(self, content):
        self.sections = []
        self.line_map = [] # Maps rendered line index to Section object
        self._parse(content)
        
    def _parse(self, content):
        lines = content.splitlines()
        re_header = re.compile(r'(TASK|PLAY|PLAY RECAP) \[.*\]')
        
        current_header = None
        current_body = []
        
        for line in lines:
            # Check if line is a header
            is_header = re_header.search(line) or 'PLAY RECAP' in line
            
            if is_header:
                # Save previous section
                self.sections.append(LogSection(current_header, current_body))
                # Start new section
                current_header = line
                current_body = []
            else:
                current_body.append(line)
                
        # Append final section
        self.sections.append(LogSection(current_header, current_body))

    def render(self):
        """
        Reconstructs the full text based on collapsed state.
        Populates self.line_map to map line indices to sections.
        """
        rendered_lines = []
        self.line_map = []
        
        for section in self.sections:
            if section.header is None:
                # Preamble (no header) - always shown
                for line in section.body:
                    rendered_lines.append(line)
                    self.line_map.append(section)
            else:
                # Header line
                header_text = section.header
                if section.collapsed:
                    header_text += " ..."
                
                rendered_lines.append(header_text)
                self.line_map.append(section)
                
                # Body lines (only if not collapsed)
                if not section.collapsed:
                    for line in section.body:
                        rendered_lines.append(line)
                        self.line_map.append(section)
                        
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
