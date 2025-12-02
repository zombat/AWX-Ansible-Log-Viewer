from prompt_toolkit.styles import Style
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl

style = Style.from_dict({
    'status': 'bg:#ffffff #000000',
    'bottom-bar': 'bg:#ffffff #000000', 
    'key': 'bg:#ffffff #000000 bold',
    'desc': 'bg:#ffffff #000000',
    'filter': 'bg:#ffff00 #000000 bold',
    
    'log.header': '#00afff bold',
    'log.error': '#ff0000 bold',
    'log.changed': '#d7ff00',
    'log.success': '#00ff00',
    'log.skip': '#00d7ff',
    'log.normal': '#cccccc',
})

def create_status_bar(log_buffer, filename, manager):
    """Create the status bar showing file info, cursor position, and filters."""
    def get_status_bar_text():
        row = log_buffer.document.cursor_position_row + 1
        total = log_buffer.document.line_count
        
        parts = [
            ('class:status', f"  AWX Viewer 1.0  File: {filename}  "),
        ]
        
        # Show active filters
        filters = []
        if manager.filter_hosts:
            host_list = ', '.join(sorted(manager.filter_hosts)[:3])
            if len(manager.filter_hosts) > 3:
                host_list += f' +{len(manager.filter_hosts)-3}'
            filters.append(f"Hosts:[{host_list}]")
        if manager.filter_tasks:
            task_list = ', '.join(sorted(manager.filter_tasks)[:2])
            if len(manager.filter_tasks) > 2:
                task_list += f' +{len(manager.filter_tasks)-2}'
            filters.append(f"Tasks:[{task_list}]")
        if manager.filter_statuses:
            status_list = ', '.join(sorted(manager.filter_statuses))
            filters.append(f"Status:[{status_list}]")
        
        if filters:
            parts.append(('class:filter', f" {' | '.join(filters)} "))
        
        parts.append(('class:status', f"Line: {row}/{total}".rjust(20)))
        
        return parts
    
    return Window(
        content=FormattedTextControl(get_status_bar_text),
        height=1,
        style='class:status'
    )

def create_bottom_bar():
    """Create the bottom bar with key binding help."""
    def get_bottom_bar():
        return [
            ('class:key', 'Q'), ('class:desc', ' Exit '),
            ('class:key', '^C'), ('class:desc', ' Copy/Exit '),
            ('class:key', 'W/S'), ('class:desc', ' Up/Dn '),
            ('class:key', 'A/D'), ('class:desc', ' Collapse/Expand '),
            ('class:key', 'F'), ('class:desc', ' Filter '),
            ('class:key', 'N'), ('class:desc', ' Next Err '),
            ('class:key', 'P'), ('class:desc', ' Prev Err '),
            ('class:key', '^R'), ('class:desc', ' Clear Filters '),
        ]
    
    return Window(
        content=FormattedTextControl(get_bottom_bar),
        height=1,
        style='class:bottom-bar'
    )
