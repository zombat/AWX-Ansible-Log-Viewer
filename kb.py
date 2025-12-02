import base64
import logging
from prompt_toolkit.key_binding import KeyBindings

def create_key_bindings(log_buffer, manager, update_buffer_callback):
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
        
        if not options:
            lines.append("  (No options available)")
        else:
            for i, option in enumerate(options):
                checkbox = '[X]' if option in selected else '[ ]'
                cursor = '> ' if i == cursor_pos else '  '
                
                # Add statistics for hosts
                if cat_idx == 0:  # Hosts category
                    stats = manager.get_host_stats(option)
                    stats_str = f" (T:{stats['total']} C:{stats['changed']} F:{stats['failed']} U:{stats['unreachable']} S:{stats['skipping']})"
                    lines.append(f"{cursor}{checkbox} {option}{stats_str}")
                else:
                    lines.append(f"{cursor}{checkbox} {option}")
        
        lines.append("")
        if cat_idx == 0:  # Show legend for hosts
            lines.append("Legend: T=Total, C=Changed, F=Failed, U=Unreachable, S=Skipped")
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
        event.app.invalidate()
    
    @filter_kb.add('down')
    def _(event):
        cat_idx = current_category[0]
        options_lists = [host_options, task_options, status_options]
        if options_lists[cat_idx]:
            cursor_positions[cat_idx] = (cursor_positions[cat_idx] + 1) % len(options_lists[cat_idx])
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
