import re
from prompt_toolkit.lexers import Lexer

class AnsibleLogLexer(Lexer):
    def __init__(self):
        super().__init__()
        self.re_task = re.compile(r'(TASK|PLAY|PLAY RECAP|RUNNING HANDLER) \[.*\]')
        self.re_fatal = re.compile(r'\b(fatal|failed):|\bFAILED\b|\bUNREACHABLE\b')
        self.re_error = re.compile(r'\b(ERROR|CRITICAL|Traceback)\b')
        self.re_changed = re.compile(r'\b(changed):')
        self.re_ok = re.compile(r'\b(ok):')
        self.re_skip = re.compile(r'\b(skipping):')
        self.re_rescued = re.compile(r'\b(rescued):')
        self.re_rec_fail = re.compile(r'failed=\d+')
        self.re_rec_unr = re.compile(r'unreachable=\d+')

    def lex_document(self, document):
        def get_line_tokens(lineno):
            line = document.lines[lineno]
            
            # Check if this is a PLAY RECAP statistics line
            if 'PLAY RECAP' not in line and re.search(r'\s+:\s+ok=\d+', line):
                # This is a stats line - tokenize it
                tokens = []
                # Match hostname part (before the colon)
                hostname_match = re.match(r'^(\S+\s*:\s+)', line)
                if hostname_match:
                    tokens.append(('class:log.normal', hostname_match.group(1)))
                    rest = line[len(hostname_match.group(1)):]
                    
                    # Parse each stat=value pair
                    parts = re.findall(r'(\w+)=(\d+)', rest)
                    pos = 0
                    for stat_name, stat_value in parts:
                        # Find this pattern in the rest string
                        pattern = f'{stat_name}={stat_value}'
                        idx = rest.find(pattern, pos)
                        if idx > pos:
                            # Add any whitespace between stats
                            tokens.append(('class:log.normal', rest[pos:idx]))
                        
                        # Color the stat based on name and value
                        value = int(stat_value)
                        if stat_name == 'ok':
                            color = 'class:log.success'  # Always green
                        elif stat_name in ['changed', 'rescued']:
                            color = 'class:log.changed' if value > 0 else 'class:log.normal'
                        elif stat_name in ['failed', 'unreachable']:
                            color = 'class:log.error' if value > 0 else 'class:log.normal'
                        elif stat_name == 'skipped':
                            color = 'class:log.skip'  # Always cyan
                        else:
                            color = 'class:log.normal'
                        
                        tokens.append((color, pattern))
                        pos = idx + len(pattern)
                    
                    # Add any remaining text
                    if pos < len(rest):
                        tokens.append(('class:log.normal', rest[pos:]))
                    
                    return tokens
            
            # Non-recap line - use single color classification
            line_type = 'class:log.normal'
            
            if 'RUNNING HANDLER' in line:
                line_type = 'class:log.handler'
            elif self.re_task.search(line):
                line_type = 'class:log.header'
            elif self.re_fatal.search(line) or self.re_error.search(line):
                line_type = 'class:log.error'
            elif self.re_changed.search(line):
                line_type = 'class:log.changed'
            elif self.re_rescued.search(line):
                line_type = 'class:log.changed'  # Use same color as changed
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
