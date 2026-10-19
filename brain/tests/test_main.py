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
