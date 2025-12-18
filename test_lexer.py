"""
Unit tests for the AnsibleLogLexer class.
"""

import unittest
from ansible_logviewer.lexer import AnsibleLogLexer
from prompt_toolkit.document import Document
from xml.dom.minidom import Document as MinidomDocument
from typing import cast

class TestAnsibleLogLexer(unittest.TestCase):
    """
    Tests for the AnsibleLogLexer class.
    
    Methods:
        setUp(): Set up the lexer instance for testing.
        test_task_line(): Test that task lines are correctly identified.
        test_fatal_line(): Test that fatal lines are correctly identified.
        test_ok_line(): Test that ok lines are correctly identified.
        test_play_recap_line(): Test that PLAY RECAP lines are correctly identified.
        test_stat_line(): Test that statistics lines are tokenized correctly.
    """

    def setUp(self):
        """Set up the lexer instance for testing."""
        self.lexer = AnsibleLogLexer()

    def test_task_line(self):
        """Test that task lines are correctly identified."""
        document = Document("TASK [example] **************************")
        tokens = self.lexer.lex_document(cast(MinidomDocument, document))(0)
        self.assertEqual(tokens[0][0], 'class:log.header')

    def test_fatal_line(self):
        """Test that fatal lines are correctly identified."""
        document = Document("fatal: [host]: FAILED! => {\"msg\": \"Some error\"}")
        tokens = self.lexer.lex_document(cast(MinidomDocument, document))(0)
        self.assertEqual(tokens[0][0], 'class:log.error')

    def test_ok_line(self):
        """Test that ok lines are correctly identified."""
        document = Document("ok: [host] => {\"msg\": \"All good\"}")
        tokens = self.lexer.lex_document(cast(MinidomDocument, document))(0)
        self.assertEqual(tokens[0][0], 'class:log.success')

    def test_play_recap_line(self):
        """Test that PLAY RECAP lines are correctly identified."""
        document = Document("PLAY RECAP *********************************************************************")
        tokens = self.lexer.lex_document(cast(MinidomDocument, document))(0)
        self.assertEqual(tokens[0][0], 'class:log.header')

    def test_stat_line(self):
        """Test that statistics lines are tokenized correctly."""
        document = Document("host : ok=2 changed=1 unreachable=0 failed=1 skipped=0 rescued=0")
        tokens = self.lexer.lex_document(cast(MinidomDocument, document))(0)
        self.assertEqual(tokens[0][0], 'class:log.normal')
        self.assertEqual(tokens[1][0], 'class:log.success')  # ok=2
        self.assertEqual(tokens[3][0], 'class:log.changed')  # changed=1
        self.assertEqual(tokens[5][0], 'class:log.normal')  # unreachable=0
        self.assertEqual(tokens[7][0], 'class:log.error')  # failed=1
        self.assertEqual(tokens[9][0], 'class:log.normal')  # skipped=0
        self.assertEqual(tokens[11][0], 'class:log.normal')  # rescued=0

if __name__ == "__main__":
    unittest.main()
