import re
from prompt_toolkit.lexers import Lexer

class AnsibleLogLexer(Lexer):
    def __init__(self):
        super().__init__()
        self.re_task = re.compile(r'(TASK|PLAY|PLAY RECAP) \[.*\]')
        self.re_fatal = re.compile(r'\b(fatal|failed):|\bFAILED\b|\bUNREACHABLE\b')
        self.re_error = re.compile(r'\b(ERROR|CRITICAL|Traceback)\b')
        self.re_changed = re.compile(r'\b(changed):')
        self.re_ok = re.compile(r'\b(ok):')
        self.re_skip = re.compile(r'\b(skipping):')
        self.re_rec_fail = re.compile(r'failed=\d+')
        self.re_rec_unr = re.compile(r'unreachable=\d+')

    def lex_document(self, document):
        def get_line_tokens(lineno):
            line = document.lines[lineno]
            line_type = 'class:log.normal'
            
            if self.re_task.search(line):
                line_type = 'class:log.header'
            elif self.re_fatal.search(line) or self.re_error.search(line):
                line_type = 'class:log.error'
            elif self.re_changed.search(line):
                line_type = 'class:log.changed'
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
