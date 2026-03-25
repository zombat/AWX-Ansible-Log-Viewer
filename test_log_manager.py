"""Unit tests for the log manager module."""

import unittest

from ansible_logviewer.log_manager import LogManager

class TestLogManager(unittest.TestCase):
    """Test log parsing, filtering, and error navigation."""

    def setUp(self):
        """Set up a sample log content and LogManager instance for testing."""
        self.sample_log = """
        TASK [Gathering Facts] *************************************************
        ok: [host1]
        TASK [Install package] ************************************************
        changed: [host1]
        TASK [Start service] **************************************************
        fatal: [host1]: FAILED! => {"msg": "Service failed to start"}
        """
        self.manager = LogManager(self.sample_log)

    def test_parse_sections(self):
        """Test that log sections are parsed correctly."""
        self.assertEqual(len(self.manager.sections), 3)
        self.assertEqual(self.manager.sections[0].task_name, "Gathering Facts")
        self.assertEqual(self.manager.sections[1].task_name, "Install package")
        self.assertEqual(self.manager.sections[2].task_name, "Start service")

    def test_filter_by_status(self):
        """Test filtering by status."""
        self.manager.set_filters(statuses={"ok"})
        filtered_content = self.manager.render()
        self.assertIn("ok: [host1]", filtered_content)
        self.assertNotIn("changed: [host1]", filtered_content)
        self.assertNotIn("fatal: [host1]", filtered_content)

    def test_find_next_error(self):
        """Test finding the next error line."""
        next_error = self.manager.find_next_error(0)
        self.assertEqual(next_error, 5)  # Line index of the fatal error

if __name__ == "__main__":
    unittest.main()