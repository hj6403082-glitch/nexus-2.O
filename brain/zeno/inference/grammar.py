"""GBNF grammars that constrain generation to a JSON schema."""

import json
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from llama_cpp.llama_grammar import json_schema_to_gbnf
from pydantic import BaseModel


def gbnf_for_schema(schema: Mapping[str, Any]) -> str:
    """Convert a JSON schema to a llama.cpp GBNF grammar."""
    return _cached(json.dumps(schema, sort_keys=True))


@lru_cache(maxsize=128)
def _cached(schema_json: str) -> str:
    return str(json_schema_to_gbnf(schema_json))


@lru_cache(maxsize=128)
def gbnf_for_model(model: type[BaseModel]) -> str:
    """Grammar for a Pydantic model's JSON schema (cached per model class)."""
    return gbnf_for_schema(model.model_json_schema())
