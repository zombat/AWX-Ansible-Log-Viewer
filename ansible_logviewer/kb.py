"""Key bindings and transient dialogs for the Ansible log viewer."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Callable, Protocol

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout


UpdateBufferCallback = Callable[[str, int], None]


class ManagerProtocol(Protocol):
    """Describe the log manager API used by key handlers."""

    all_hosts: set[str]
    all_tasks: set[str]
    filter_hosts: set[str]
    filter_tasks: set[str]
    filter_statuses: set[str]

    def toggle_section(self, line_idx: int, collapse: bool = False) -> tuple[str, int] | int:
        """Collapse or expand a section at a rendered line index."""

    def find_next_error(self, current_line_idx: int) -> int | None:
        """Return the next error line index."""

    def find_previous_error(self, current_line_idx: int) -> int | None:
        """Return the previous error line index."""

    def clear_filters(self) -> None:
        """Clear active filters."""

    def render(self) -> str:
        """Render the current view."""

    def get_statuses_ordered(self) -> list[str]:
        """Return statuses in display order."""

    def get_host_stats(self, host: str) -> dict[str, int]:
        """Return summary counts for a host."""

    def set_filters(
        self,
        hosts: set[str] | None = None,
        tasks: set[str] | None = None,
        statuses: set[str] | None = None,
    ) -> None:
        """Update active filters."""


def create_key_bindings(
    log_buffer: Buffer,
    manager: ManagerProtocol,
    update_buffer_callback: UpdateBufferCallback,
    source_filename: str | None = None,
    current_page_ref: list[int] | None = None,
    update_task_buffer: Callable[[int], None] | None = None,
) -> KeyBindings:
    """Create the main application key bindings."""
    del current_page_ref
    del update_task_buffer
    kb = KeyBindings()

    @kb.add("c-c")
    def copy_or_exit(event: KeyPressEvent) -> None:
        """Copy the active selection, or exit if nothing is selected."""
        current_buffer = event.app.current_buffer
        if current_buffer.selection_state:
            _copy_selection_to_clipboard(event, current_buffer)
            current_buffer.selection_state = None
            return
        event.app.exit()

    @kb.add("c-x")
    def exit_application(event: KeyPressEvent) -> None:
        """Exit the application immediately."""
        event.app.exit()

    @kb.add("q")
    def confirm_exit(event: KeyPressEvent) -> None:
        """Show a quit confirmation dialog."""
        show_quit_confirmation(event.app, original_kb=kb)

    @kb.add("w")
    @kb.add("up")
    def move_up(_event: KeyPressEvent) -> None:
        """Move the cursor up by one line."""
        log_buffer.cursor_up()

    @kb.add("s")
    @kb.add("down")
    def move_down(_event: KeyPressEvent) -> None:
        """Move the cursor down by one line."""
        log_buffer.cursor_down()

    @kb.add("pageup")
    def page_up(_event: KeyPressEvent) -> None:
        """Move the cursor up by a fixed page step."""
        for _ in range(10):
            log_buffer.cursor_up()

    @kb.add("pagedown")
    def page_down(_event: KeyPressEvent) -> None:
        """Move the cursor down by a fixed page step."""
        for _ in range(10):
            log_buffer.cursor_down()

    @kb.add("a")
    @kb.add("left")
    @kb.add("-")
    def collapse_section(event: KeyPressEvent) -> None:
        """Collapse the section under the cursor."""
        _toggle_current_section(event, log_buffer, manager, update_buffer_callback, collapse=True)

    @kb.add("d")
    @kb.add("right")
    @kb.add("+")
    def expand_section(event: KeyPressEvent) -> None:
        """Expand the section under the cursor."""
        _toggle_current_section(event, log_buffer, manager, update_buffer_callback, collapse=False)

    @kb.add("f")
    def open_filter_dialog(event: KeyPressEvent) -> None:
        """Show the filter dialog."""
        show_filter_dialog(event.app, manager, update_buffer_callback)

    @kb.add("S")
    @kb.add("c-s")
    def save_filtered_view(event: KeyPressEvent) -> None:
        """Show a save dialog for the current filtered text."""
        show_save_dialog(event.app, log_buffer, source_filename)

    @kb.add("n")
    def next_error(event: KeyPressEvent) -> None:
        """Jump to the next failed or unreachable line."""
        _jump_to_error(event, log_buffer, manager.find_next_error)

    @kb.add("p")
    def previous_error(event: KeyPressEvent) -> None:
        """Jump to the previous failed or unreachable line."""
        _jump_to_error(event, log_buffer, manager.find_previous_error)

    @kb.add("c-r")
    def clear_filters(event: KeyPressEvent) -> None:
        """Clear all active filters and redraw the full log."""
        manager.clear_filters()
        update_buffer_callback(manager.render(), 0)
        event.app.invalidate()

    return kb


def _copy_selection_to_clipboard(event: KeyPressEvent, current_buffer: Buffer) -> None:
    """Copy the selected text to the terminal clipboard using OSC 52."""
    selection = current_buffer.copy_selection()
    text = selection.text

    try:
        encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
        event.app.output.write_raw(f"\x1b]52;c;{encoded}\x07")
        event.app.output.flush()
    except (AttributeError, OSError, UnicodeError) as error:
        logging.error("Failed to copy selection: %s", error)


def _toggle_current_section(
    event: KeyPressEvent,
    log_buffer: Buffer,
    manager: ManagerProtocol,
    update_buffer_callback: UpdateBufferCallback,
    *,
    collapse: bool,
) -> None:
    """Toggle the current section and redraw when the manager returns new text."""
    current_line = log_buffer.document.cursor_position_row
    result = manager.toggle_section(current_line, collapse=collapse)
    if isinstance(result, tuple):
        update_buffer_callback(*result)
        event.app.invalidate()


def _jump_to_error(
    event: KeyPressEvent,
    log_buffer: Buffer,
    resolver: Callable[[int], int | None],
) -> None:
    """Resolve an error line and move the cursor to it when present."""
    current_line = log_buffer.document.cursor_position_row
    target_line = resolver(current_line)
    if target_line is None:
        return

    log_buffer.cursor_position = log_buffer.document.translate_row_col_to_index(target_line, 0)
    event.app.invalidate()


def show_filter_dialog(app: Any, manager: ManagerProtocol, update_buffer_callback: UpdateBufferCallback) -> None:
    """Show a multi-category filter dialog."""
    host_options = sorted(manager.all_hosts)
    task_options = sorted(manager.all_tasks)
    status_options = manager.get_statuses_ordered()

    selected_hosts = set(manager.filter_hosts)
    selected_tasks = set(manager.filter_tasks)
    selected_statuses = set(manager.filter_statuses)
    current_category = [0]
    cursor_positions = [0, 0, 0]
    scroll_offsets = [0, 0, 0]
    terminal_height = app.output.get_size().rows
    max_visible_items = max(5, terminal_height - 10)
    original_layout = app.layout
    original_key_bindings = app.key_bindings

    def get_filter_text() -> str:
        """Render the currently selected filter category."""
        categories = ["Hosts", "Tasks", "Statuses"]
        options_lists = [host_options, task_options, status_options]
        selected_lists = [selected_hosts, selected_tasks, selected_statuses]
        category_index = current_category[0]
        options = options_lists[category_index]
        selected = selected_lists[category_index]
        cursor_position = cursor_positions[category_index]
        scroll_offset = scroll_offsets[category_index]

        lines = [
            f"Filter by {categories[category_index]} (Press TAB to switch categories)",
            "=" * 70,
            "",
        ]

        if not options:
            lines.append("  (No options available)")
        else:
            total_items = len(options)
            start_index = scroll_offset
            end_index = min(start_index + max_visible_items, total_items)

            if total_items > max_visible_items:
                lines.append(
                    f"  Showing {start_index + 1}-{end_index} of {total_items} (scroll with UP/DOWN)"
                )
                lines.append("")

            for index in range(start_index, end_index):
                option = options[index]
                checkbox = "[X]" if option in selected else "[ ]"
                cursor = "> " if index == cursor_position else "  "
                if category_index == 0:
                    stats = manager.get_host_stats(option)
                    stats_text = (
                        f" (T:{stats['total']} C:{stats['changed']} F:{stats['failed']} "
                        f"U:{stats['unreachable']} S:{stats['skipping']} R:{stats['rescued']})"
                    )
                    lines.append(f"{cursor}{checkbox} {option}{stats_text}")
                else:
                    lines.append(f"{cursor}{checkbox} {option}")

        lines.append("")
        if category_index == 0:
            lines.append("Legend: T=Total, C=Changed, F=Failed, U=Unreachable, S=Skipped, R=Rescued")
        lines.append("Navigation: UP/DOWN to move, SPACE to toggle, TAB to switch category")
        lines.append("Actions: ENTER to apply, ESC to cancel, C to clear all, A to select all")
        return "\n".join(lines)

    def restore() -> None:
        """Restore the application layout after closing the dialog."""
        app.layout = original_layout
        app.key_bindings = original_key_bindings
        app.invalidate()

    def move_cursor(delta: int) -> None:
        """Move the category cursor and keep it in the visible window."""
        category_index = current_category[0]
        options_lists = [host_options, task_options, status_options]
        if not options_lists[category_index]:
            return

        cursor_positions[category_index] = (
            cursor_positions[category_index] + delta
        ) % len(options_lists[category_index])

        if cursor_positions[category_index] < scroll_offsets[category_index]:
            scroll_offsets[category_index] = cursor_positions[category_index]
        elif cursor_positions[category_index] >= scroll_offsets[category_index] + max_visible_items:
            scroll_offsets[category_index] = cursor_positions[category_index] - max_visible_items + 1

    filter_kb = KeyBindings()

    @filter_kb.add("up")
    def filter_up(event: KeyPressEvent) -> None:
        """Move the filter cursor up."""
        move_cursor(-1)
        event.app.invalidate()

    @filter_kb.add("down")
    def filter_down(event: KeyPressEvent) -> None:
        """Move the filter cursor down."""
        move_cursor(1)
        event.app.invalidate()

    @filter_kb.add("tab")
    def filter_next_category(event: KeyPressEvent) -> None:
        """Switch to the next filter category."""
        current_category[0] = (current_category[0] + 1) % 3
        event.app.invalidate()

    @filter_kb.add("space")
    def toggle_filter_item(event: KeyPressEvent) -> None:
        """Toggle the selected item in the active filter category."""
        options_lists = [host_options, task_options, status_options]
        selected_lists = [selected_hosts, selected_tasks, selected_statuses]
        category_index = current_category[0]
        options = options_lists[category_index]
        if options:
            selected = selected_lists[category_index]
            item = options[cursor_positions[category_index]]
            if item in selected:
                selected.remove(item)
            else:
                selected.add(item)
        event.app.invalidate()

    @filter_kb.add("a")
    def select_all_in_category(event: KeyPressEvent) -> None:
        """Select all options in the active category."""
        category_index = current_category[0]
        [selected_hosts, selected_tasks, selected_statuses][category_index].update(
            [host_options, task_options, status_options][category_index]
        )
        event.app.invalidate()

    @filter_kb.add("c")
    def clear_category(event: KeyPressEvent) -> None:
        """Clear selections in the active category."""
        [selected_hosts, selected_tasks, selected_statuses][current_category[0]].clear()
        event.app.invalidate()

    @filter_kb.add("enter")
    def apply_filters(_event: KeyPressEvent) -> None:
        """Apply dialog selections and restore the main layout."""
        manager.set_filters(
            hosts=selected_hosts or None,
            tasks=selected_tasks or None,
            statuses=selected_statuses or None,
        )
        update_buffer_callback(manager.render(), 0)
        restore()

    @filter_kb.add("escape")
    @filter_kb.add("c-x")
    def cancel_filters(_event: KeyPressEvent) -> None:
        """Close the dialog without changing filter state."""
        restore()

    dialog_container = HSplit(
        [
            Window(height=1),
            VSplit([Window(width=5), Window(content=FormattedTextControl(get_filter_text)), Window(width=5)]),
        ]
    )
    app.layout = Layout(dialog_container)
    app.key_bindings = filter_kb


def show_quit_confirmation(app: Any, original_kb: KeyBindings) -> None:
    """Show a confirmation dialog before exiting."""
    original_layout = app.layout

    def get_confirm_text() -> str:
        """Return the confirmation prompt text."""
        return "\n  Are you sure you want to quit?\n\n  Press Y to quit, N or ESC to cancel\n"

    confirm_kb = KeyBindings()

    @confirm_kb.add("y")
    @confirm_kb.add("Y")
    def quit_confirmed(event: KeyPressEvent) -> None:
        """Exit the application from the confirmation dialog."""
        event.app.exit()

    @confirm_kb.add("n")
    @confirm_kb.add("N")
    @confirm_kb.add("escape")
    def cancel_quit(_event: KeyPressEvent) -> None:
        """Restore the previous layout without exiting."""
        app.layout = original_layout
        app.key_bindings = original_kb
        app.invalidate()

    dialog_container = HSplit(
        [
            Window(height=10),
            VSplit([Window(width=20), Window(content=FormattedTextControl(lambda: "=" * 50), height=1)]),
            VSplit([Window(width=20), Window(content=FormattedTextControl(get_confirm_text), height=6)]),
            VSplit([Window(width=20), Window(content=FormattedTextControl(lambda: "=" * 50), height=1)]),
        ]
    )
    app.layout = Layout(dialog_container)
    app.key_bindings = confirm_kb


def show_save_dialog(app: Any, log_buffer: Buffer, source_filename: str | None = None) -> None:
    """Show a prompt to save the current rendered log view to disk."""
    original_layout = app.layout
    original_key_bindings = app.key_bindings
    default_name = "filtered.log"
    if source_filename:
        base = os.path.basename(source_filename)
        name, extension = os.path.splitext(base)
        default_name = f"{name}.filtered{extension}" if extension else f"{name}.filtered.log"

    title_window = Window(
        content=FormattedTextControl(
            lambda: "\n  Save filtered view to file\n\n  Enter filename (default: filtered.log) and press Enter\n"
        ),
        height=5,
    )
    input_buffer = Buffer(document=Document(default_name, 0))
    input_window = Window(content=BufferControl(buffer=input_buffer, focusable=True), height=1)
    status_message = [""]
    status_window = Window(content=FormattedTextControl(lambda: status_message[0]), height=1)
    dialog_container = HSplit(
        [
            Window(height=1),
            VSplit([Window(width=5), HSplit([title_window, input_window, status_window]), Window(width=5)]),
        ]
    )

    def restore() -> None:
        """Restore the main layout after the save dialog closes."""
        app.layout = original_layout
        app.key_bindings = original_key_bindings
        app.invalidate()

    save_kb = KeyBindings()

    @save_kb.add("enter")
    def save_file(_event: KeyPressEvent) -> None:
        """Write the current buffer contents to the selected file."""
        filename = input_buffer.text.strip() or "filtered.log"
        try:
            with open(filename, "w", encoding="utf-8", errors="replace") as output_file:
                output_file.write(log_buffer.document.text)
            status_message[0] = f"Saved to {filename}"
        except OSError as error:
            status_message[0] = f"Error: {error}"
        app.invalidate()
        restore()

    @save_kb.add("escape")
    @save_kb.add("c-x")
    def cancel_save(_event: KeyPressEvent) -> None:
        """Close the save dialog without writing a file."""
        restore()

    app.layout = Layout(dialog_container)
    app.key_bindings = save_kb
    app.layout.focus(input_window)
