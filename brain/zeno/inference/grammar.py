"""GBNF grammars that constrain generation to a JSON schema."""

import json
import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from llama_cpp.llama_grammar import json_schema_to_gbnf
from pydantic import BaseModel


def gbnf_for_schema(schema: Mapping[str, Any]) -> str:
    """Convert a JSON schema to a llama.cpp GBNF grammar.

    Properties keep their declared order, which is the order the model generates
    them in (so a "thought" field declared first is written first).
    """
    return _cached(json.dumps(schema))


# llama-cpp-python's converter lets strings contain raw control characters, which
# JSON forbids, so a model could emit text no JSON parser accepts. This is the
# stricter rule current llama.cpp uses.
_LOOSE_CHAR = r'char ::= [^"\\] |'
_JSON_CHAR = r'char ::= [^"\\\x7F\x00-\x1F] |'


# The converter copies regex escapes such as \. and \- from "pattern" into the grammar,
# but llama.cpp's grammar parser only knows these escapes and rejects the rest
# (Python's LlamaGrammar.from_string is laxer and lets them through).
_GBNF_ESCAPES = frozenset('xuUtrn\\"[]')
_ESCAPE = re.compile(r"\\(.)", re.DOTALL)


def _portable_escape(match: re.Match[str]) -> str:
    char = match.group(1)
    return match.group(0) if char in _GBNF_ESCAPES else f"\\x{ord(char):02X}"


@lru_cache(maxsize=128)
def _cached(schema_json: str) -> str:
    grammar = str(json_schema_to_gbnf(schema_json))
    grammar = _ESCAPE.sub(_portable_escape, grammar)
    return grammar.replace(_LOOSE_CHAR, _JSON_CHAR)


@lru_cache(maxsize=128)
def gbnf_for_model(model: type[BaseModel]) -> str:
    """Grammar for a Pydantic model's JSON schema (cached per model class)."""
    return gbnf_for_schema(model.model_json_schema())
