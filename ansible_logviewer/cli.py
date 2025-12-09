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
from .log_manager import LogManager
from .lexer import AnsibleLogLexer
from .ui import style, create_status_bar, create_bottom_bar
from .kb import create_key_bindings

# Configure logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG, filemode='w', format='%(asctime)s - %(message)s')


def main():
    parser = argparse.ArgumentParser(description="Nano-style AWX Log Viewer")
    parser.add_argument('filename', help="Path to the AWX/Ansible log file")
    parser.add_argument('--highlight-style', choices=['underline', 'color', 'both'], default='underline', help="Highlight style for search matches")
    parser.add_argument('--search-mode', choices=['keyword', 'regex', 'both'], default='both', help="Search mode: keyword, regex, or both")
    args = parser.parse_args()

    try:
        with open(args.filename, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except FileNotFoundError:
        content = "File not found."

    # Initialize Manager
    manager = LogManager(content)
    initial_text = manager.render()

    # Prepare search state (to be used for search integration)
    search_state = {
        'query': None,
        'matches': [],
        'current_idx': 0,
        'highlight_style': args.highlight_style,
        'search_mode': args.search_mode,
        'case_sensitive': False,
        'off_page_matches': 0
    }

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

    # Initialize pagination state
    current_page = 1
    page_size = 10  # Number of tasks per page

    def update_task_buffer(page):
        """Update the buffer with tasks for the given page."""
        nonlocal current_page
        tasks, total_pages = manager.get_tasks_by_page(page, page_size)
        if not tasks:
            return  # Do nothing if the page is invalid

        current_page = page
        task_text = "\n".join(tasks)
        update_buffer(task_text, 0)  # Update buffer with tasks
        logging.debug(f"Task buffer updated to page {current_page}/{total_pages}")

    # Pass current_page as a mutable reference
    current_page_ref = [current_page]

    # Highlighting lexer wrapper
    class HighlightingLexer:
        def __init__(self, base_lexer, matches, style):
            self.base_lexer = base_lexer
            self.matches = matches
            self.style = style
        def invalidation_hash(self):
            # Hash includes matches tuple to invalidate cache when matches change
            return (id(self.base_lexer), tuple(self.matches), self.style)
        def lex_document(self, document):
            base_lex_func = self.base_lexer.lex_document(document)
            def get_line(lineno):
                # Get base tokens from the original lexer
                base_tokens = base_lex_func(lineno)
                tokens = list(base_tokens)
                
                # Find matches in this line
                line_start = document.translate_row_col_to_index(lineno, 0)
                line_end = line_start + len(document.lines[lineno])
                line_matches = [(start, end) for start, end in self.matches if start < line_end and end > line_start]
                
                if not line_matches:
                    return tokens
                
                # Apply highlighting to overlapping regions
                new_tokens = []
                for ttype, val in tokens:
                    # Calculate position of this token in the buffer
                    token_start = line_start + sum(len(v) for _, v in new_tokens)
                    token_end = token_start + len(val)
                    
                    # Check if this token overlaps with any match
                    overlaps = [m for m in line_matches if m[0] < token_end and m[1] > token_start]
                    
                    if overlaps:
                        if self.style == 'underline':
                            new_ttype = ttype + ' underline'
                        elif self.style == 'color':
                            new_ttype = ttype + ' class:search-match'
                        elif self.style == 'both':
                            new_ttype = ttype + ' underline class:search-match'
                        else:
                            new_ttype = ttype
                        new_tokens.append((new_ttype, val))
                    else:
                        new_tokens.append((ttype, val))
                
                return new_tokens
            return get_line

    # Highlighting lexer wrapper
    class HighlightingLexer:
        def __init__(self, base_lexer, matches, style):
            self.base_lexer = base_lexer
            self.matches = matches
            self.style = style
        def invalidation_hash(self):
            # Hash includes matches tuple to invalidate cache when matches change
            return (id(self.base_lexer), tuple(self.matches), self.style)
        def lex_document(self, document):
            base_lex_func = self.base_lexer.lex_document(document)
            def get_line(lineno):
                # Get base tokens from the original lexer
                base_tokens = base_lex_func(lineno)
                tokens = list(base_tokens)
                
                # Find matches in this line
                line_start = document.translate_row_col_to_index(lineno, 0)
                line_end = line_start + len(document.lines[lineno])
                line_matches = [(start, end) for start, end in self.matches if start < line_end and end > line_start]
                
                if not line_matches:
                    return tokens
                
                # Apply highlighting to overlapping regions
                new_tokens = []
                for ttype, val in tokens:
                    # Calculate position of this token in the buffer
                    token_start = line_start + sum(len(v) for _, v in new_tokens)
                    token_end = token_start + len(val)
                    
                    # Check if this token overlaps with any match
                    overlaps = [m for m in line_matches if m[0] < token_end and m[1] > token_start]
                    
                    if overlaps:
                        if self.style == 'underline':
                            new_ttype = ttype + ' underline'
                        elif self.style == 'color':
                            new_ttype = ttype + ' class:search-match'
                        elif self.style == 'both':
                            new_ttype = ttype + ' underline class:search-match'
                        else:
                            new_ttype = ttype
                        new_tokens.append((new_ttype, val))
                    else:
                        new_tokens.append((ttype, val))
                
                return new_tokens
            return get_line

    # Search prompt and logic
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.shortcuts import input_dialog
    from prompt_toolkit.application.current import get_app
    from prompt_toolkit.widgets import TextArea, Frame
    from prompt_toolkit.layout.containers import VSplit

    import asyncio
    import re
    original_lexer = AnsibleLogLexer()  # Keep reference to original lexer
    
    def show_search_dialog():
        """Show search dialog using a layout overlay instead of a nested application."""
        app = get_app()
        original_layout = app.layout
        original_kb = app.key_bindings
        
        def restore_app():
            app.layout = original_layout
            app.key_bindings = original_kb
            app.invalidate()
            try:
                app.layout.focus(log_control)
            except Exception as e:
                logging.warning(f"Focus error: {e}")

        def accept_search(buff):
            query = buff.text
            restore_app()
            
            if query:
                search_state['query'] = query
                logging.info(f"Search query entered: {query}")
                
                # Search logic
                text = log_buffer.document.text
                matches = []
                flags = 0 if search_state['case_sensitive'] else re.IGNORECASE
                pattern = query
                
                if search_state['search_mode'] == 'regex' or (search_state['search_mode'] == 'both' and re.search(r'[.*+?^${}()\[\]|]', query)):
                    try:
                        for m in re.finditer(pattern, text, flags):
                            matches.append((m.start(), m.end()))
                    except re.error as e:
                        logging.error(f"Regex error: {e}")
                else:
                    # Keyword search
                    idx = 0
                    while True:
                        idx = text.lower().find(query.lower(), idx) if not search_state['case_sensitive'] else text.find(query, idx)
                        if idx == -1:
                            break
                        matches.append((idx, idx + len(query)))
                        idx += len(query)
                
                search_state['matches'] = matches
                search_state['current_idx'] = 0
                
                if matches:
                    log_control.lexer = HighlightingLexer(original_lexer, matches, search_state['highlight_style'])
                else:
                    log_control.lexer = original_lexer
            else:
                log_control.lexer = original_lexer
                search_state['matches'] = []

        search_field = TextArea(
            multiline=False,
            accept_handler=accept_search,
            prompt='Search: ',
            style='class:search-field'
        )
        
        # Dialog specific key bindings
        dialog_kb = KeyBindings()
        @dialog_kb.add('escape')
        def _(event):
            restore_app()
            
        # Layout
        dialog_window = Frame(
            search_field,
            title="Search (Enter to find, Esc to cancel)",
            width=60,
            height=4
        )
        
        dialog_container = HSplit([
            Window(),
            VSplit([Window(), dialog_window, Window()]),
            Window()
        ])
        
        app.layout = Layout(dialog_container)
        app.key_bindings = dialog_kb
        app.layout.focus(search_field)

    # Extend key bindings
    kb = create_key_bindings(log_buffer, manager, update_buffer, args.filename, current_page_ref, update_task_buffer)
    # Add Ctrl+F and '/' for search
    try:
        @kb.add('c-f')
        def _(event):
            show_search_dialog()
        @kb.add('/')
        def _(event):
            show_search_dialog()
            
        @kb.add('c-r')
        def _(event):
            # Clear search
            search_state['query'] = None
            search_state['matches'] = []
            log_control.lexer = original_lexer
            
            # Clear filters
            manager.clear_filters()
            new_text = manager.render()
            update_buffer(new_text, 0)
            
            event.app.invalidate()
    except Exception as e:
        logging.error(f"Error adding search key bindings: {e}")

    # Create UI components
    status_bar = create_status_bar(log_buffer, args.filename, manager)
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
