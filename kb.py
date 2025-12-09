import base64
import logging
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.containers import Window, HSplit, VSplit
from prompt_toolkit.layout.layout import Layout

def create_key_bindings(log_buffer, manager, update_buffer_callback, source_filename=None, current_page_ref=None, update_task_buffer=None):
    """Create and configure all key bindings for the application."""
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
    
    @kb.add('q')
    def _(event):
        "Quit application with confirmation."
        show_quit_confirmation(event.app, original_kb=kb)

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
            update_buffer_callback(*res)
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
            update_buffer_callback(*res)
            event.app.invalidate()
            logging.debug(f"Buffer updated and invalidated, new line count: {log_buffer.document.line_count}")

    @kb.add('f')
    def _(event):
        "Open filter dialog"
        show_filter_dialog(event.app, manager, log_buffer, update_buffer_callback)

    @kb.add('S')
    @kb.add('c-s')
    def _(event):
        "Save filtered view"
        show_save_dialog(event.app, log_buffer, source_filename)

    @kb.add('n')
    def _(event):
        "Jump to next error (failed/unreachable)"
        current_line = log_buffer.document.cursor_position_row
        next_error_line = manager.find_next_error(current_line)
        if next_error_line is not None:
            new_cursor_pos = log_buffer.document.translate_row_col_to_index(next_error_line, 0)
            log_buffer.cursor_position = new_cursor_pos
            event.app.invalidate()

    @kb.add('p')
    def _(event):
        "Jump to previous error (failed/unreachable)"
        current_line = log_buffer.document.cursor_position_row
        prev_error_line = manager.find_previous_error(current_line)
        if prev_error_line is not None:
            new_cursor_pos = log_buffer.document.translate_row_col_to_index(prev_error_line, 0)
            log_buffer.cursor_position = new_cursor_pos
            event.app.invalidate()

    @kb.add('c-r')
    def _(event):
        "Clear all filters"
        manager.clear_filters()
        new_text = manager.render()
        update_buffer_callback(new_text, 0)
        event.app.invalidate()

    return kb

def show_filter_dialog(app, manager, log_buffer, update_buffer_callback):
    """Show a dialog to set filters with multi-select support."""
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.layout.containers import Window, HSplit, VSplit
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.widgets import Box
    
    # Build filter options
    host_options = sorted(manager.all_hosts)
    task_options = sorted(manager.all_tasks)
    status_options = manager.get_statuses_ordered()  # Use ordered statuses
    
    # Track selected items (copy current filters)
    selected_hosts = set(manager.filter_hosts)
    selected_tasks = set(manager.filter_tasks)
    selected_statuses = set(manager.filter_statuses)
    
    # Track which category we're viewing: 0=hosts, 1=tasks, 2=statuses
    current_category = [0]
    # Track cursor position within each category
    cursor_positions = [0, 0, 0]
    # Track scroll offset for pagination within each category
    scroll_offsets = [0, 0, 0]
    
    # Get terminal height for pagination
    terminal_height = app.output.get_size().rows
    # Reserve space for header (3 lines), footer (4 lines), and padding
    max_visible_items = max(5, terminal_height - 10)
    
    def get_filter_text():
        categories = ['Hosts', 'Tasks', 'Statuses']
        options_lists = [host_options, task_options, status_options]
        selected_lists = [selected_hosts, selected_tasks, selected_statuses]
        
        cat_idx = current_category[0]
        lines = []
        lines.append(f"Filter by {categories[cat_idx]} (Press TAB to switch categories)")
        lines.append("="* 70)
        lines.append("")
        
        options = options_lists[cat_idx]
        selected = selected_lists[cat_idx]
        cursor_pos = cursor_positions[cat_idx]
        scroll_offset = scroll_offsets[cat_idx]
        
        if not options:
            lines.append("  (No options available)")
        else:
            total_items = len(options)
            
            # Calculate visible range with pagination
            start_idx = scroll_offset
            end_idx = min(start_idx + max_visible_items, total_items)
            
            # Show pagination indicator if needed
            if total_items > max_visible_items:
                lines.append(f"  Showing {start_idx + 1}-{end_idx} of {total_items} (scroll with UP/DOWN)")
                lines.append("")
            
            for i in range(start_idx, end_idx):
                option = options[i]
                checkbox = '[X]' if option in selected else '[ ]'
                cursor = '> ' if i == cursor_pos else '  '
                
                # Add statistics for hosts
                if cat_idx == 0:  # Hosts category
                    stats = manager.get_host_stats(option)
                    stats_str = f" (T:{stats['total']} C:{stats['changed']} F:{stats['failed']} U:{stats['unreachable']} S:{stats['skipping']} R:{stats['rescued']})"
                    lines.append(f"{cursor}{checkbox} {option}{stats_str}")
                else:
                    lines.append(f"{cursor}{checkbox} {option}")
        
        lines.append("")
        if cat_idx == 0:  # Show legend for hosts
            lines.append("Legend: T=Total, C=Changed, F=Failed, U=Unreachable, S=Skipped, R=Rescued")
        lines.append("Navigation: UP/DOWN to move, SPACE to toggle, TAB to switch category")
        lines.append("Actions: ENTER to apply, ESC to cancel, C to clear all, A to select all")
        
        return '\n'.join(lines)
    
    # Store original layout and key bindings
    original_layout = app.layout
    original_key_bindings = app.key_bindings
    
    # Create filter dialog key bindings
    filter_kb = KeyBindings()
    
    @filter_kb.add('up')
    def _(event):
        cat_idx = current_category[0]
        options_lists = [host_options, task_options, status_options]
        if options_lists[cat_idx]:
            cursor_positions[cat_idx] = (cursor_positions[cat_idx] - 1) % len(options_lists[cat_idx])
            
            # Adjust scroll offset to keep cursor visible
            if cursor_positions[cat_idx] < scroll_offsets[cat_idx]:
                scroll_offsets[cat_idx] = cursor_positions[cat_idx]
            elif cursor_positions[cat_idx] >= scroll_offsets[cat_idx] + max_visible_items:
                scroll_offsets[cat_idx] = cursor_positions[cat_idx] - max_visible_items + 1
        event.app.invalidate()
    
    @filter_kb.add('down')
    def _(event):
        cat_idx = current_category[0]
        options_lists = [host_options, task_options, status_options]
        if options_lists[cat_idx]:
            cursor_positions[cat_idx] = (cursor_positions[cat_idx] + 1) % len(options_lists[cat_idx])
            
            # Adjust scroll offset to keep cursor visible
            if cursor_positions[cat_idx] < scroll_offsets[cat_idx]:
                scroll_offsets[cat_idx] = cursor_positions[cat_idx]
            elif cursor_positions[cat_idx] >= scroll_offsets[cat_idx] + max_visible_items:
                scroll_offsets[cat_idx] = cursor_positions[cat_idx] - max_visible_items + 1
        event.app.invalidate()
    
    @filter_kb.add('tab')
    def _(event):
        current_category[0] = (current_category[0] + 1) % 3
        event.app.invalidate()
    
    @filter_kb.add('space')
    def _(event):
        cat_idx = current_category[0]
        options_lists = [host_options, task_options, status_options]
        selected_lists = [selected_hosts, selected_tasks, selected_statuses]
        
        options = options_lists[cat_idx]
        selected = selected_lists[cat_idx]
        cursor_pos = cursor_positions[cat_idx]
        
        if options:
            item = options[cursor_pos]
            if item in selected:
                selected.remove(item)
            else:
                selected.add(item)
        event.app.invalidate()
    
    @filter_kb.add('a')
    def _(event):
        cat_idx = current_category[0]
        options_lists = [host_options, task_options, status_options]
        selected_lists = [selected_hosts, selected_tasks, selected_statuses]
        
        # Select all in current category
        selected_lists[cat_idx].update(options_lists[cat_idx])
        event.app.invalidate()
    
    @filter_kb.add('c')
    def _(event):
        # Clear all in current category
        cat_idx = current_category[0]
        selected_lists = [selected_hosts, selected_tasks, selected_statuses]
        selected_lists[cat_idx].clear()
        event.app.invalidate()
    
    @filter_kb.add('enter')
    def _(event):
        # Apply filters
        manager.set_filters(
            hosts=selected_hosts if selected_hosts else None,
            tasks=selected_tasks if selected_tasks else None,
            statuses=selected_statuses if selected_statuses else None
        )
        new_text = manager.render()
        update_buffer_callback(new_text, 0)
        
        # Restore original layout and key bindings
        app.layout = original_layout
        app.key_bindings = original_key_bindings
        app.invalidate()
    
    @filter_kb.add('escape')
    @filter_kb.add('c-x')
    def _(event):
        # Cancel without applying
        app.layout = original_layout
        app.key_bindings = original_key_bindings
        app.invalidate()
    
    # Create filter dialog layout
    filter_control = FormattedTextControl(text=get_filter_text)
    filter_window = Window(content=filter_control)
    
    # Create a simple centered dialog
    dialog_container = HSplit([
        Window(height=1),  # Top spacer
        VSplit([
            Window(width=5),  # Left spacer
            filter_window,
            Window(width=5),  # Right spacer
        ]),
    ])
    
    # Replace layout and key bindings
    app.layout = Layout(dialog_container)
    app.key_bindings = filter_kb

def show_quit_confirmation(app, original_kb):
    """Show a confirmation dialog before quitting."""
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.layout.containers import Window, HSplit, VSplit
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.key_binding import KeyBindings
    
    # Store original layout and key bindings
    original_layout = app.layout
    
    def get_confirm_text():
        return (
            "\n"
            "  Are you sure you want to quit?\n"
            "\n"
            "  Press Y to quit, N or ESC to cancel\n"
        )
    
    # Create confirmation dialog key bindings
    confirm_kb = KeyBindings()
    
    @confirm_kb.add('y')
    @confirm_kb.add('Y')
    def _(event):
        event.app.exit()
    
    @confirm_kb.add('n')
    @confirm_kb.add('N')
    @confirm_kb.add('escape')
    def _(event):
        # Cancel - restore original layout and key bindings
        app.layout = original_layout
        app.key_bindings = original_kb
        app.invalidate()
    
    # Create confirmation dialog layout
    confirm_control = FormattedTextControl(text=get_confirm_text)
    confirm_window = Window(content=confirm_control, height=6)
    
    dialog_container = HSplit([
        Window(height=10),  # Top spacer
        VSplit([
            Window(width=20),  # Left spacer
            Window(content=FormattedTextControl(text=lambda: "=" * 50), height=1),
        ]),
        VSplit([
            Window(width=20),  # Left spacer
            confirm_window,
        ]),
        VSplit([
            Window(width=20),  # Left spacer
            Window(content=FormattedTextControl(text=lambda: "=" * 50), height=1),
        ]),
    ])
    
    # Replace layout and key bindings
    app.layout = Layout(dialog_container)
    app.key_bindings = confirm_kb

def show_save_dialog(app, log_buffer, source_filename=None):
    """Show a dialog to save current filtered text to a file."""
    original_layout = app.layout
    original_key_bindings = app.key_bindings
    import os
    # Derive smart default filename
    default_name = "filtered.log"
    if source_filename:
        base = os.path.basename(source_filename)
        name, ext = os.path.splitext(base)
        if ext:
            default_name = f"{name}.filtered{ext}"
        else:
            default_name = f"{name}.filtered.log"

    title_control = FormattedTextControl(text=lambda: (
        "\n  Save filtered view to file\n\n  Enter filename (default: filtered.log) and press Enter\n"
    ))
    title_window = Window(content=title_control, height=5)

    input_buffer = Buffer(document=Document(default_name, 0))
    input_control = BufferControl(buffer=input_buffer, focusable=True)
    input_window = Window(content=input_control, height=1)

    status_msg = [""]
    status_control = FormattedTextControl(text=lambda: status_msg[0])
    status_window = Window(content=status_control, height=1)

    dialog_container = HSplit([
        Window(height=1),
        VSplit([
            Window(width=5),
            HSplit([
                title_window,
                input_window,
                status_window,
            ]),
            Window(width=5),
        ]),
    ])

    kb_save = KeyBindings()

    @kb_save.add('enter')
    def _(event):
        filename = input_buffer.text.strip() or "filtered.log"
        try:
            with open(filename, 'w', encoding='utf-8', errors='replace') as f:
                f.write(log_buffer.document.text)
            status_msg[0] = f"Saved to {filename}"
        except Exception as e:
            status_msg[0] = f"Error: {e}"
        app.invalidate()
        # Close after brief feedback
        app.layout = original_layout
        app.key_bindings = original_key_bindings
        app.invalidate()

    @kb_save.add('escape')
    @kb_save.add('c-x')
    def _(event):
        app.layout = original_layout
        app.key_bindings = original_key_bindings
        app.invalidate()

    app.layout = Layout(dialog_container)
    app.key_bindings = kb_save
    # Ensure the filename input has focus for typing
    try:
        app.layout.focus(input_control)
    except Exception:
        # Fallback: focus the input window
        app.layout.focus(input_window)
