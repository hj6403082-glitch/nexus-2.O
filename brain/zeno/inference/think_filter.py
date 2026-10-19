"""Strips ``<think>…</think>`` blocks from streamed text across arbitrary chunk splits."""

_OPEN = "<think>"
_CLOSE = "</think>"


class ThinkFilter:
    def __init__(self) -> None:
        self._inside = False
        self._carry = ""

    def push(self, text: str) -> str:
        data, out = self._carry + text, []
        self._carry = ""
        while data:
            tag = _CLOSE if self._inside else _OPEN
            at = data.find(tag)
            if at >= 0:
                if not self._inside:
                    out.append(data[:at])
                data = data[at + len(tag) :]
                self._inside = not self._inside
                continue
            keep = _partial_tag_suffix(data, tag)
            if not self._inside:
                out.append(data[: len(data) - keep])
            self._carry = data[len(data) - keep :]
            data = ""
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self._inside else self._carry
        self._carry = ""
        return rest


def _partial_tag_suffix(data: str, tag: str) -> int:
    """Length of the longest suffix of ``data`` that could be the start of ``tag``."""
    for k in range(min(len(tag) - 1, len(data)), 0, -1):
        if tag.startswith(data[-k:]):
            return k
    return 0
