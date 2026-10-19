"""GET /v1/status: what the brain is running and whether it is ready."""

from typing import Any

from tests.api.conftest import Brain


def test_status_when_ready(make_brain: Any) -> None:
    brain: Brain = make_brain()
    status = brain.client.get("/v1/status").json()
    assert status["state"] == "ready"
    assert status["model"] == "model.gguf"
    assert "calculate" in status["tools"]
    assert "remember_fact" in status["tools"]
    assert status["devices"] == []
    assert status["message"]


def test_status_needs_no_token_but_reveals_no_secrets(make_brain: Any) -> None:
    brain: Brain = make_brain()
    body = brain.client.get("/v1/status").text
    assert brain.token not in body


def test_there_are_no_docs_or_openapi_endpoints(make_brain: Any) -> None:
    brain: Brain = make_brain()
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert brain.client.get(path).status_code == 404
