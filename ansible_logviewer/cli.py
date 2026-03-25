"""Command-line entry point for the Ansible log viewer."""

from __future__ import annotations

import argparse
import logging
import re
from typing import Any, Callable

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.widgets import Frame, TextArea

from .kb import create_key_bindings
from .lexer import AnsibleLogLexer
from .log_manager import LogManager
from .ui import create_bottom_bar, create_status_bar, style


logging.getLogger(__name__).addHandler(logging.NullHandler())

SearchState = dict[str, Any]


def update_buffer(log_buffer: Buffer, new_text: str, new_cursor_idx: int) -> None:
    """Replace the visible buffer text and reposition the cursor."""
    try:
        logging.debug(
            "update_buffer called with cursor_idx=%d, text length=%d",
            new_cursor_idx,
            len(new_text),
        )
        log_buffer.read_only = lambda: False
        log_buffer.document = Document(new_text, 0)
        log_buffer.read_only = lambda: True
        new_cursor_pos = log_buffer.document.translate_row_col_to_index(new_cursor_idx, 0)
        log_buffer.cursor_position = new_cursor_pos
    except (AttributeError, IndexError, ValueError) as error:
        logging.error("Error in update_buffer: %s", error, exc_info=True)


class HighlightingLexer:
    """Wrap a base lexer and overlay search result highlighting."""

    def __init__(self, base_lexer: AnsibleLogLexer, matches: list[tuple[int, int]], highlight_style: str) -> None:
        """Store the wrapped lexer and current match state."""
        self.base_lexer = base_lexer
        self.matches = matches
        self.highlight_style = highlight_style

    def invalidation_hash(self) -> tuple[int, tuple[tuple[int, int], ...], str]:
        """Return a stable cache key that changes when search results change."""
        return (id(self.base_lexer), tuple(self.matches), self.highlight_style)

    def lex_document(self, document: Document) -> Callable[[int], list[tuple[str, str]]]:
        """Apply search highlighting on top of the wrapped lexer output."""
        base_line_getter = self.base_lexer.lex_document(document)

        def get_line(lineno: int) -> list[tuple[str, str]]:
            """Return styled tokens for one line with any overlapping search hits highlighted."""
            base_tokens = list(base_line_getter(lineno))
            line_start = document.translate_row_col_to_index(lineno, 0)
            line_end = line_start + len(document.lines[lineno])
            line_matches = [
                (start, end) for start, end in self.matches if start < line_end and end > line_start
            ]
            if not line_matches:
                return base_tokens

            new_tokens: list[tuple[str, str]] = []
            for token_type, value in base_tokens:
                token_start = line_start + sum(len(existing_value) for _, existing_value in new_tokens)
                token_end = token_start + len(value)
                overlaps = [match for match in line_matches if match[0] < token_end and match[1] > token_start]
                new_tokens.append((self._highlight_token_type(token_type) if overlaps else token_type, value))
            return new_tokens

        return get_line

    def _highlight_token_type(self, token_type: str) -> str:
        """Append the configured search highlight style to a token class."""
        if self.highlight_style == "underline":
            return f"{token_type} underline"
        if self.highlight_style == "color":
            return f"{token_type} class:search-match"
        if self.highlight_style == "both":
            return f"{token_type} underline class:search-match"
        return token_type


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Nano-style AWX Log Viewer")
    parser.add_argument("filename", help="Path to the AWX/Ansible log file")
    parser.add_argument(
        "--highlight-style",
        choices=["underline", "color", "both"],
        default="underline",
        help="Highlight style for search matches",
    )
    parser.add_argument(
        "--search-mode",
        choices=["keyword", "regex", "both"],
        default="both",
        help="Search mode: keyword, regex, or both",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write debug output to debug.log in the current directory",
    )
    return parser


def _load_content(filename: str) -> str:
    """Load file contents, returning a visible fallback message on failure."""
    try:
        with open(filename, "r", encoding="utf-8", errors="replace") as input_file:
            return input_file.read()
    except FileNotFoundError:
        return "File not found."


def _find_matches(text: str, search_state: SearchState, query: str) -> list[tuple[int, int]]:
    """Find search matches using keyword or regex mode."""
    matches: list[tuple[int, int]] = []
    flags = 0 if search_state["case_sensitive"] else re.IGNORECASE
    use_regex = search_state["search_mode"] == "regex" or (
        search_state["search_mode"] == "both" and bool(re.search(r"[.*+?^${}()\[\]|]", query))
    )

    if use_regex:
        try:
            for match in re.finditer(query, text, flags):
                matches.append((match.start(), match.end()))
        except re.error as error:
            logging.error("Regex error: %s", error)
        return matches

    search_text = text if search_state["case_sensitive"] else text.lower()
    search_query = query if search_state["case_sensitive"] else query.lower()
    index = 0
    while True:
        index = search_text.find(search_query, index)
        if index == -1:
            return matches
        matches.append((index, index + len(query)))
        index += len(query)


def _install_search_bindings(
    key_bindings: KeyBindings,
    *,
    log_buffer: Buffer,
    log_control: BufferControl,
    manager: LogManager,
    original_lexer: AnsibleLogLexer,
    search_state: SearchState,
    update_buffer_callback: Callable[[str, int], None],
) -> None:
    """Attach search-specific key bindings to the main application map."""

    def show_search_dialog() -> None:
        """Show a search dialog by temporarily swapping the application layout."""
        app = get_app()
        original_layout = app.layout
        original_key_bindings = app.key_bindings

        def restore() -> None:
            """Restore the main layout and refocus the log window."""
            app.layout = original_layout
            app.key_bindings = original_key_bindings
            app.invalidate()
            app.layout.focus(log_control)

        def accept_search(search_buffer: Buffer) -> None:
            """Apply a new search query and update the lexer highlights."""
            query = search_buffer.text
            restore()
            if not query:
                search_state["query"] = None
                search_state["matches"] = []
                log_control.lexer = original_lexer
                return

            search_state["query"] = query
            search_state["matches"] = _find_matches(log_buffer.document.text, search_state, query)
            search_state["current_idx"] = 0
            if search_state["matches"]:
                log_control.lexer = HighlightingLexer(
                    original_lexer,
                    search_state["matches"],
                    search_state["highlight_style"],
                )
            else:
                log_control.lexer = original_lexer

        search_field = TextArea(
            multiline=False,
            accept_handler=accept_search,
            prompt="Search: ",
            style="class:search-field",
        )
        dialog_kb = KeyBindings()

        @dialog_kb.add("escape")
        def cancel_search(_event: KeyPressEvent) -> None:
            """Close the search dialog without changing the search state."""
            restore()

        dialog_window = Frame(search_field, title="Search (Enter to find, Esc to cancel)", width=60, height=4)
        dialog_container = HSplit([Window(), VSplit([Window(), dialog_window, Window()]), Window()])
        app.layout = Layout(dialog_container)
        app.key_bindings = dialog_kb
        app.layout.focus(search_field)

    @key_bindings.add("c-f")
    def show_search_from_ctrl_f(_event: KeyPressEvent) -> None:
        """Open the search dialog from Ctrl+F."""
        show_search_dialog()

    @key_bindings.add("/")
    def show_search_from_slash(_event: KeyPressEvent) -> None:
        """Open the search dialog from slash."""
        show_search_dialog()

    @key_bindings.add("c-r")
    def clear_search_and_filters(event: KeyPressEvent) -> None:
        """Clear search highlights and active filters together."""
        search_state["query"] = None
        search_state["matches"] = []
        log_control.lexer = original_lexer
        manager.clear_filters()
        update_buffer_callback(manager.render(), 0)
        event.app.invalidate()


def main() -> None:
    """Run the full-screen prompt_toolkit application."""
    args = _build_parser().parse_args()
    if args.debug:
        logging.basicConfig(
            filename="debug.log",
            level=logging.DEBUG,
            filemode="w",
            format="%(asctime)s - %(message)s",
        )
    manager = LogManager(_load_content(args.filename))
    initial_text = manager.render()
    search_state: SearchState = {
        "query": None,
        "matches": [],
        "current_idx": 0,
        "highlight_style": args.highlight_style,
        "search_mode": args.search_mode,
        "case_sensitive": False,
        "off_page_matches": 0,
    }
    log_buffer = Buffer(document=Document(initial_text, 0), read_only=Condition(lambda: True), multiline=True)

    def update_buffer_wrapper(new_text: str, new_cursor_idx: int) -> None:
        """Bind the generic buffer updater to the main log buffer instance."""
        update_buffer(log_buffer, new_text, new_cursor_idx)

    log_control = BufferControl(buffer=log_buffer, lexer=AnsibleLogLexer(), focusable=True)
    log_window = Window(content=log_control, wrap_lines=False, cursorline=True)
    current_page_ref = [1]
    page_size = 10

    def update_task_buffer(page: int) -> None:
        """Replace the buffer with a paginated list of task names."""
        tasks, total_pages = manager.get_tasks_by_page(page, page_size)
        if not tasks:
            return
        current_page_ref[0] = page
        update_buffer_wrapper("\n".join(tasks), 0)
        logging.debug("Task buffer updated for page %d/%d", page, total_pages)

    original_lexer = AnsibleLogLexer()
    log_control.lexer = original_lexer
    key_bindings = create_key_bindings(
        log_buffer,
        manager,
        update_buffer_wrapper,
        args.filename,
        current_page_ref,
        update_task_buffer,
    )
    _install_search_bindings(
        key_bindings,
        log_buffer=log_buffer,
        log_control=log_control,
        manager=manager,
        original_lexer=original_lexer,
        search_state=search_state,
        update_buffer_callback=update_buffer_wrapper,
    )

    root_container = HSplit(
        [
            create_status_bar(log_buffer, args.filename, manager),
            log_window,
            create_bottom_bar(),
        ]
    )
    app = Application(
        layout=Layout(root_container),
        key_bindings=key_bindings,
        style=style,
        full_screen=True,
        mouse_support=True,
    )
    app.run()


if __name__ == "__main__":
    main()
