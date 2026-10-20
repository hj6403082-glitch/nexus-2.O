"""The model list both setup scripts read (brain/model-downloads.txt)."""

from pathlib import Path
from urllib.parse import urlparse

LIST = Path(__file__).parents[1] / "model-downloads.txt"


def entries() -> list[list[str]]:
    lines = LIST.read_text(encoding="utf-8").splitlines()
    return [line.split() for line in lines if line.strip() and not line.startswith("#")]


def test_every_entry_is_a_group_a_file_and_an_https_url() -> None:
    rows = entries()
    assert rows
    for row in rows:
        assert len(row) == 3, row
        group, name, url = row
        assert group in {"vision", "voice"}
        assert "/" not in name and "\\" not in name and not name.startswith(".")
        parsed = urlparse(url)
        assert parsed.scheme == "https" and parsed.hostname == "huggingface.co"
        assert parsed.path.endswith("/" + name)


def test_file_names_are_unique() -> None:
    names = [name for _, name, _ in entries()]
    assert len(names) == len(set(names))


def test_vision_ships_a_model_and_its_projector_and_voice_a_whisper_and_a_piper_model() -> None:
    by_group: dict[str, list[str]] = {}
    for group, name, _ in entries():
        by_group.setdefault(group, []).append(name)
    assert any("mmproj" in n for n in by_group["vision"])
    assert any(n.endswith(".gguf") and "mmproj" not in n for n in by_group["vision"])
    assert any(n.startswith("ggml-") and n.endswith(".bin") for n in by_group["voice"])
    onnx = [n for n in by_group["voice"] if n.endswith(".onnx")]
    assert onnx and all(f"{n}.json" in by_group["voice"] for n in onnx)  # Piper needs both
