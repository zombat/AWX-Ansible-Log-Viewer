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

    return kb
