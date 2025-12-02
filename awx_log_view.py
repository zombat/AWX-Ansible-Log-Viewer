import sys
import argparse
import re
import logging
import base64
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.filters import Condition

# Configure logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG, filemode='w', format='%(asctime)s - %(message)s')

# -----------------------------------------------------------------------------
# 1. LOG MANAGER (Parsing & State)
# -----------------------------------------------------------------------------

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

# -----------------------------------------------------------------------------
# 2. LEXER
# -----------------------------------------------------------------------------

class AnsibleLogLexer(Lexer):
    def __init__(self):
        super().__init__()
        self.re_task = re.compile(r'(TASK|PLAY|PLAY RECAP) \[.*\]')
        self.re_fatal = re.compile(r'\b(fatal|failed):|\bFAILED\b|\bUNREACHABLE\b')
        self.re_error = re.compile(r'\b(ERROR|CRITICAL|Traceback)\b')
        self.re_changed = re.compile(r'\b(changed):')
        self.re_ok = re.compile(r'\b(ok):')
        self.re_skip = re.compile(r'\b(skipping):')
        self.re_rec_fail = re.compile(r'failed=\d+')
        self.re_rec_unr = re.compile(r'unreachable=\d+')

    def lex_document(self, document):
        def get_line_tokens(lineno):
            line = document.lines[lineno]
            line_type = 'class:log.normal'
            
            if self.re_task.search(line):
                line_type = 'class:log.header'
            elif self.re_fatal.search(line) or self.re_error.search(line):
                line_type = 'class:log.error'
            elif self.re_changed.search(line):
                line_type = 'class:log.changed'
            elif self.re_ok.search(line):
                line_type = 'class:log.success'
            elif self.re_skip.search(line):
                line_type = 'class:log.skip'
            
            if 'PLAY RECAP' in line:
                 line_type = 'class:log.header'
            elif (self.re_rec_fail.search(line) and 'failed=0' not in line) or \
                 (self.re_rec_unr.search(line) and 'unreachable=0' not in line):
                line_type = 'class:log.error'
                
            return [(line_type, line)]
            
        return get_line_tokens

# -----------------------------------------------------------------------------
# 3. UI STYLING
# -----------------------------------------------------------------------------

style = Style.from_dict({
    'status': 'bg:#ffffff #000000',
    'bottom-bar': 'bg:#ffffff #000000', 
    'key': 'bg:#ffffff #000000 bold',
    'desc': 'bg:#ffffff #000000',
    
    'log.header': '#00afff bold',
    'log.error': '#ff0000 bold',
    'log.changed': '#d7ff00',
    'log.success': '#00ff00',
    'log.skip': '#00d7ff',
    'log.normal': '#cccccc',
})

# -----------------------------------------------------------------------------
# 4. MAIN APPLICATION
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nano-style AWX Log Viewer")
    parser.add_argument('filename', help="Path to the AWX/Ansible log file")
    args = parser.parse_args()

    try:
        with open(args.filename, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except FileNotFoundError:
        content = "File not found."

    # Initialize Manager
    manager = LogManager(content)
    initial_text = manager.render()

    # Create Buffer (not read_only so we can update it programmatically)
    log_buffer = Buffer(
        document=Document(initial_text, 0),
        read_only=Condition(lambda: True),  # Always read-only for user input
        multiline=True
    )
    
    # Collapsing
    def update_buffer(new_text, new_cursor_idx):
        try:
            logging.debug(f"update_buffer called with cursor_idx={new_cursor_idx}, text length={len(new_text)}")
            # Temporarily disable read-only to update document
            log_buffer.read_only = lambda: False
            log_buffer.document = Document(new_text, 0)
            # Re-enable read-only
            log_buffer.read_only = lambda: True
            logging.debug(f"Document updated, line_count={log_buffer.document.line_count}")
            # Move cursor to the header of the section
            new_cursor_pos = log_buffer.document.translate_row_col_to_index(new_cursor_idx, 0)
            logging.debug(f"Cursor position calculated: {new_cursor_pos}")
            log_buffer.cursor_position = new_cursor_pos
            logging.debug(f"Buffer updated successfully: {log_buffer.document.line_count} lines, cursor at line {new_cursor_idx}")
        except Exception as e:
            logging.error(f"Error in update_buffer: {e}", exc_info=True)
    
    log_control = BufferControl(
        buffer=log_buffer,
        lexer=AnsibleLogLexer(),
        focusable=True
    )
    
    log_window = Window(
        content=log_control,
        wrap_lines=False,
        cursorline=True
    )

    # Key Bindings
    kb = KeyBindings()

    @kb.add('c-c')
    def _(event):
        "Copy selection if active, else quit."
        buff = event.app.current_buffer
        if buff.selection_state:
            # Copy to internal clipboard
            data = buff.copy_selection() 
            text = data.text
            
            # Try to copy to system clipboard using OSC 52
            try:
                encoded = base64.b64encode(text.encode('utf-8')).decode('utf-8')
                event.app.output.write_raw(f"\x1b]52;c;{encoded}\x07")
                event.app.output.flush()
            except Exception as e:
                logging.error(f"Failed to copy: {e}")
                
            # Clear selection
            buff.selection_state = None
        else:
            event.app.exit()

    @kb.add('c-x')
    def _(event):
        "Quit application."
        event.app.exit()

    # Navigation
    @kb.add('w')
    @kb.add('up')
    def _(event):
        log_buffer.cursor_up()

    @kb.add('s')
    @kb.add('down')
    def _(event):
        log_buffer.cursor_down()

    @kb.add('pageup')
    def _(event):
        for _ in range(10):
            log_buffer.cursor_up()

    @kb.add('pagedown')
    def _(event):
        for _ in range(10):
            log_buffer.cursor_down()

    @kb.add('a')
    @kb.add('left')
    @kb.add('-')
    def _(event):
        "Collapse current section"
        current_line = log_buffer.document.cursor_position_row
        logging.debug(f"Collapse requested at line {current_line}")
        res = manager.toggle_section(current_line, collapse=True)
        logging.debug(f"toggle_section returned: {type(res)} = {res if not isinstance(res, tuple) else (res[1], len(res[0]))}")
        if isinstance(res, tuple):
            logging.debug("Calling update_buffer...")
            update_buffer(*res)
            event.app.invalidate()
            logging.debug(f"Buffer updated and invalidated, new line count: {log_buffer.document.line_count}")

    @kb.add('d')
    @kb.add('right')
    @kb.add('+')
    def _(event):
        "Expand current section"
        current_line = log_buffer.document.cursor_position_row
        logging.debug(f"Expand requested at line {current_line}")
        res = manager.toggle_section(current_line, collapse=False)
        logging.debug(f"toggle_section returned: {type(res)} = {res if not isinstance(res, tuple) else (res[1], len(res[0]))}")
        if isinstance(res, tuple):
            logging.debug("Calling update_buffer...")
            update_buffer(*res)
            event.app.invalidate()
            logging.debug(f"Buffer updated and invalidated, new line count: {log_buffer.document.line_count}")

    # Layout Components
    def get_status_bar_text():
        row = log_buffer.document.cursor_position_row + 1
        total = log_buffer.document.line_count
        return [
            ('class:status', f"  AWX Viewer 1.0  File: {args.filename}  "),
            ('class:status', f"Line: {row}/{total}".rjust(40))
        ]

    status_bar = Window(
        content=FormattedTextControl(get_status_bar_text),
        height=1,
        style='class:status'
    )

    def get_bottom_bar():
        return [
            ('class:key', '^X'), ('class:desc', ' Exit '),
            ('class:key', '^C'), ('class:desc', ' Copy/Exit '),
            ('class:key', 'W/S'), ('class:desc', ' Up/Dn '),
            ('class:key', 'A/D'), ('class:desc', ' Collapse/Expand '),
        ]

    bottom_bar = Window(
        content=FormattedTextControl(get_bottom_bar),
        height=1,
        style='class:bottom-bar'
    )

    root_container = HSplit([
        status_bar,
        log_window,
        bottom_bar
    ])

    layout = Layout(root_container)

    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=True,
        mouse_support=True
    )

    app.run()

if __name__ == "__main__":
    main()
