"""Unit tests for UI helper functions."""

import unittest
from unittest.mock import Mock

from prompt_toolkit.buffer import Buffer

from ansible_logviewer.ui import create_bottom_bar, create_status_bar

class TestUI(unittest.TestCase):
    """Test bottom and status bar construction."""

    def setUp(self):
        """Set up mock objects for testing."""
        self.mock_buffer = Mock(spec=Buffer)
        self.mock_buffer.document.cursor_position_row = 5
        self.mock_buffer.document.line_count = 100
        self.mock_manager = Mock()
        self.mock_manager.filter_hosts = {"host1", "host2"}
        self.mock_manager.filter_tasks = {"task1"}
        self.mock_manager.filter_statuses = {"ok", "failed"}

    def test_create_status_bar(self):
        """Test the create_status_bar function."""
        status_bar = create_status_bar(self.mock_buffer, "test.log", self.mock_manager)
        self.assertIsNotNone(status_bar)
        self.assertEqual(status_bar.style, "class:status")

    def test_create_bottom_bar(self):
        """Test the create_bottom_bar function."""
        bottom_bar = create_bottom_bar()
        self.assertIsNotNone(bottom_bar)
        self.assertEqual(bottom_bar.style, "class:bottom-bar")

if __name__ == "__main__":
    unittest.main()