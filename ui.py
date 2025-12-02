from prompt_toolkit.styles import Style
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl

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

def create_status_bar(log_buffer, filename):
    """Create the status bar showing file info and cursor position."""
    def get_status_bar_text():
        row = log_buffer.document.cursor_position_row + 1
        total = log_buffer.document.line_count
        return [
            ('class:status', f"  AWX Viewer 1.0  File: {filename}  "),
            ('class:status', f"Line: {row}/{total}".rjust(40))
        ]
    
    return Window(
        content=FormattedTextControl(get_status_bar_text),
        height=1,
        style='class:status'
    )

def create_bottom_bar():
    """Create the bottom bar with key binding help."""
    def get_bottom_bar():
        return [
            ('class:key', '^X'), ('class:desc', ' Exit '),
            ('class:key', '^C'), ('class:desc', ' Copy/Exit '),
            ('class:key', 'W/S'), ('class:desc', ' Up/Dn '),
            ('class:key', 'A/D'), ('class:desc', ' Collapse/Expand '),
        ]
    
    return Window(
        content=FormattedTextControl(get_bottom_bar),
        height=1,
        style='class:bottom-bar'
    )
