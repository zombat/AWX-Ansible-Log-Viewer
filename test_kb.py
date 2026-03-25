"""
Unit tests for the key bindings in ansible_logviewer.kb module.
"""

import unittest
from unittest.mock import Mock

from prompt_toolkit.buffer import Buffer

from ansible_logviewer.kb import create_key_bindings

class TestKeyBindings(unittest.TestCase):
    """
    Tests for the key bindings in the ansible_logviewer.kb module.
    
    Methods:
        setUp(): Set up the mock objects and key bindings for testing.
        test_copy_selection(): Test the 'Ctrl-C' key binding for copying selection.
        test_quit_application(): Test the 'Ctrl-X' key binding for quitting the application.
        test_navigation_up(): Test the 'Up' key binding for navigating up.
        test_navigation_down(): Test the 'Down' key binding for navigating down.
    """

    def setUp(self):
        """Set up the mock objects and key bindings for testing."""
        self.mock_buffer = Mock(spec=Buffer)
        self.mock_manager = Mock()
        self.mock_update_callback = Mock()
        self.key_bindings = create_key_bindings(
            log_buffer=self.mock_buffer,
            manager=self.mock_manager,
            update_buffer_callback=self.mock_update_callback
        )

    def test_copy_selection(self):
        """Test the 'Ctrl-C' key binding for copying selection."""
        event = Mock()
        event.app.current_buffer = self.mock_buffer
        self.mock_buffer.selection_state = True
        self.mock_buffer.copy_selection.return_value.text = "copied text"

        handler = self.key_bindings.get_bindings_for_keys(("c-c",))[0].handler
        handler(event)

        self.mock_buffer.copy_selection.assert_called_once()
        self.assertIsNone(self.mock_buffer.selection_state)

    def test_quit_application(self):
        """Test the 'Ctrl-X' key binding for quitting the application."""
        event = Mock()
        event.app.exit = Mock()

        handler = self.key_bindings.get_bindings_for_keys(("c-x",))[0].handler
        handler(event)

        event.app.exit.assert_called_once()

    def test_navigation_up(self):
        """Test the 'Up' key binding for navigating up."""
        event = Mock()
        handler = self.key_bindings.get_bindings_for_keys(("up",))[0].handler
        handler(event)

        self.mock_buffer.cursor_up.assert_called_once()

    def test_navigation_down(self):
        """Test the 'Down' key binding for navigating down."""
        event = Mock()
        handler = self.key_bindings.get_bindings_for_keys(("down",))[0].handler
        handler(event)

        self.mock_buffer.cursor_down.assert_called_once()

if __name__ == "__main__":
    unittest.main()
