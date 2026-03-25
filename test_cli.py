"""
Unit tests for the CLI module in ansible_logviewer.
"""

import unittest
from unittest.mock import Mock, patch

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document

from ansible_logviewer.cli import main, update_buffer

class TestCLI(unittest.TestCase):
    """
    Tests for the CLI module in ansible_logviewer.
    
    Methods:
        test_main_with_valid_file(): Test the main function with a valid file.
        test_main_with_missing_file(): Test the main function when the file is missing.
        test_update_buffer(): Test the update_buffer function.
    """
    
    # patching argparse and open to simulate command line arguments and file reading

    @patch("argparse.ArgumentParser.parse_args")
    @patch("builtins.open")
    def test_main_with_valid_file(self, mock_open, mock_args):
        """Test the main function with a valid file."""
        mock_args.return_value = Mock(
            filename="test.log",
            highlight_style="underline",
            search_mode="both"
        )
        mock_open.return_value.__enter__.return_value.read.return_value = "Sample log content"

        with patch("ansible_logviewer.cli.Application.run") as mock_run:
            main()
            mock_run.assert_called_once()

    @patch("argparse.ArgumentParser.parse_args")
    @patch("builtins.open")
    def test_main_with_missing_file(self, mock_open, mock_args):
        """Test the main function when the file is missing."""
        mock_args.return_value = Mock(
            filename="missing.log",
            highlight_style="underline",
            search_mode="both"
        )
        mock_open.side_effect = FileNotFoundError

        with patch("ansible_logviewer.cli.Application.run") as mock_run:
            main()
            mock_run.assert_called_once()

    def test_update_buffer(self):
        """Test the update_buffer function."""
        mock_buffer = Mock(spec=Buffer)
        mock_buffer.document = Document("Initial content")

        def mock_read_only():
            return False

        mock_buffer.read_only = mock_read_only

        new_text = "Updated content"
        new_cursor_idx = 1

        with patch("ansible_logviewer.cli.logging.debug") as mock_debug:
            update_buffer(mock_buffer, new_text, new_cursor_idx)
            mock_debug.assert_called()
            self.assertEqual(mock_buffer.document.text, new_text)
            self.assertEqual(mock_buffer.cursor_position, 0)

if __name__ == "__main__":
    unittest.main()
