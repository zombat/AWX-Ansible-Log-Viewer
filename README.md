AWX/Ansible Log Viewer

A fast, keyboard-driven terminal UI for exploring AWX/Ansible logs. It supports multi-select filtering (hosts, tasks, statuses), quick error navigation, and a clean status/bottom bar experience powered by prompt_toolkit.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-yellow)](https://buymeacoffee.com/raymondandrewrizzo)

Features
- Multi-select filters: choose multiple hosts, tasks, and statuses at once.
- Ordered statuses: always shows ok, changed, unreachable, failed, skipping.
- Host stats in dialog: per-host T/C/F/U/S counts for quick triage.
- Error navigation: jump to next/previous failed or unreachable line.
- Collapsing/expanding: fold sections to focus on what matters.
- Copy selection: Ctrl+C copies selected text via OSC 52 when possible.
- Safe exit: Q prompts for confirmation; Ctrl+X exits immediately.

Requirements
- Python 3.10+
- prompt_toolkit 3.x

Install
```bash
# Install from PyPI
pip install ansible-logviewer

# Run
ansible-logviewer path/to/logfile.log
```

Or install from source:
```bash
# (optional) create a virtualenv
python3 -m venv .venv
source .venv/bin/activate

pip install .
```

Key Bindings
- Q: Exit (with confirmation)
- Ctrl+X: Exit immediately
- Ctrl+C: Copy selection (or exit when no selection)
- W / Up: Move up
- S / Down: Move down
- PageUp / PageDown: Scroll by blocks
- A / Left / -: Collapse current section
- D / Right / +: Expand current section
- F: Open filter dialog
- N: Next error (failed/unreachable)
- P: Previous error (failed/unreachable)
- Ctrl+R: Clear all filters

Filter Dialog
- Categories: Hosts, Tasks, Statuses (TAB switches categories)
- Navigation: Up/Down to move; Space to toggle selection
- Actions: A (select all), C (clear), Enter (apply), ESC/Ctrl+X (cancel)
- Host stats legend: T=Total, C=Changed, F=Failed, U=Unreachable, S=Skipped

Notes
- Status list is always shown in order: ok, changed, unreachable, failed, skipping (even if some don’t appear in the current file).
- Error navigation respects active filters and collapsed state (errors in collapsed sections won’t appear in the rendered body until expanded).

Options
- `--highlight-style underline|color|both`: Style for search match highlights (default: underline)
- `--search-mode keyword|regex|both`: Search mode (default: both)
- `--debug`: Write debug output to `debug.log` in the current directory

Troubleshooting
- If Ctrl+X doesn’t work in your terminal, use Q (with prompt) to exit.
- If copying via Ctrl+C doesn’t reach the system clipboard, your terminal may not support OSC 52; the text is still copied internally.

Project Structure
- ansible_logviewer/cli.py: application entrypoint and UI wiring
- ansible_logviewer/log_manager.py: parsing, indexing, filtering, and navigation logic
- ansible_logviewer/kb.py: key bindings and modal dialogs
- ansible_logviewer/ui.py: styles and status/bottom bar rendering
- ansible_logviewer/lexer.py: syntax highlighting for log lines

Contributing
- PRs welcome; please keep changes minimal and aligned with the existing coding style.
- GitHub: [zombat/AWX-Ansible-Log-Viewer](https://github.com/zombat/AWX-Ansible-Log-Viewer)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

Raymond Rizzo
