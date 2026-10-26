"""``python -m zeno``: run the brain, or print the chat API token."""

from pathlib import Path

import pytest

from tests.api.conftest import brain_settings
from zeno.__main__ import main


def test_token_is_created_once_and_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = brain_settings(tmp_path)
    assert main(["token"], settings) == 0
    first = capsys.readouterr().out.strip().splitlines()[-1]
    assert main(["token"], settings) == 0
    second = capsys.readouterr().out.strip().splitlines()[-1]
    assert first == second == settings.api_token_file.read_text(encoding="utf-8").strip()
    assert len(first) >= 32


def test_without_a_console_logs_go_to_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import logging

    from zeno.__main__ import configure_logging

    settings = brain_settings(tmp_path, log_file=tmp_path / "logs" / "zeno.log")
    root = logging.getLogger()
    before = list(root.handlers)
    monkeypatch.setattr("sys.stderr", None)  # what pythonw (the Windows logon task) gives
    try:
        assert configure_logging(settings) == settings.log_file
        logging.getLogger("zeno.test").warning("hello from the logon task")
        for handler in root.handlers:
            handler.flush()
        assert "hello from the logon task" in settings.log_file.read_text(encoding="utf-8")
    finally:
        for handler in root.handlers[:]:
            if handler not in before:
                root.removeHandler(handler)
                handler.close()


def test_with_a_console_logs_go_to_stderr(tmp_path: Path) -> None:
    from zeno.__main__ import configure_logging

    assert configure_logging(brain_settings(tmp_path)) is None
