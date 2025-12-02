import argparse
import logging
from prompt_toolkit.application import Application
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition

# Import custom modules
from log_manager import LogManager
from lexer import AnsibleLogLexer
from ui import style, create_status_bar, create_bottom_bar
from kb import create_key_bindings

# Configure logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG, filemode='w', format='%(asctime)s - %(message)s')


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

    # Create key bindings with dependencies
    kb = create_key_bindings(log_buffer, manager, update_buffer)

    # Create UI components
    status_bar = create_status_bar(log_buffer, args.filename)
    bottom_bar = create_bottom_bar()

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
