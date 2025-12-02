import sys
import argparse
import re
import logging
import pandas as pd
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.layout.controls import FormattedTextControl

# Configure logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG, filemode='w', format='%(asctime)s - %(message)s')

# -----------------------------------------------------------------------------
# 1. LOG PARSING & LEXER
# -----------------------------------------------------------------------------

class AnsibleLogLexer(Lexer):
    def __init__(self):
        super().__init__()
        # Regex patterns for Ansible status
        self.re_task = re.compile(r'(TASK|PLAY|PLAY RECAP) \[.*\]')
        # Updated to match FAILED, UNREACHABLE, fatal:, failed:
        self.re_fatal = re.compile(r'\b(fatal|failed):|\bFAILED\b|\bUNREACHABLE\b')
        self.re_error = re.compile(r'\b(ERROR|CRITICAL|Traceback)\b')
        self.re_changed = re.compile(r'\b(changed):')
        self.re_ok = re.compile(r'\b(ok):')
        self.re_skip = re.compile(r'\b(skipping):')
        self.re_rec_ok = re.compile(r'ok=\d+')
        self.re_rec_chg = re.compile(r'changed=\d+')
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
# 2. UI STYLING
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
# 3. APPLICATION LOGIC
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

    # Create Buffer with Lexer
    # Buffer handles cursor movement and scrolling automatically
    log_buffer = Buffer(
        document=Document(content, 0),
        read_only=True, # Prevent editing
        multiline=True
    )
    
    log_control = BufferControl(
        buffer=log_buffer,
        lexer=AnsibleLogLexer(),
        focusable=True
    )
    
    log_window = Window(
        content=log_control,
        wrap_lines=False,
        cursorline=True # Highlight current line
    )

    # Key Bindings
    kb = KeyBindings()

    @kb.add('c-c')
    @kb.add('c-x')
    def _(event):
        "Quit application."
        event.app.exit()

    # BufferControl handles Up/Down/PgUp/PgDn automatically if focused!
    # But we want to support 'w' and 'd' as well.
    
    @kb.add('w')
    def _(event):
        log_buffer.cursor_up()

    @kb.add('s')
    def _(event):
        log_buffer.cursor_down()

    # Layout Components
    def get_status_bar_text():
        # Get current line from buffer cursor
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
            ('class:key', '^X'), ('class:desc', ' Exit      '),
            ('class:key', 'PgUp'), ('class:desc', ' Prev Page '),
            ('class:key', 'PgDn'), ('class:desc', ' Next Page '),
            ('class:key', 'Arrows/WS'), ('class:desc', ' Scroll   '),
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
