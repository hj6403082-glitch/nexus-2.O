"""GBNF grammars that constrain generation to a JSON schema."""

import json
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


@lru_cache(maxsize=128)
def _cached(schema_json: str) -> str:
    grammar = str(json_schema_to_gbnf(schema_json))
    return grammar.replace(_LOOSE_CHAR, _JSON_CHAR)


@lru_cache(maxsize=128)
def gbnf_for_model(model: type[BaseModel]) -> str:
    """Grammar for a Pydantic model's JSON schema (cached per model class)."""
    return gbnf_for_schema(model.model_json_schema())
