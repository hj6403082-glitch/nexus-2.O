"""The chat socket: messages in, the agent's reasoning streamed out."""

import json
from typing import Any

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.agent.conftest import act, final
from tests.api.conftest import (
    Brain,
    approve,
    connect,
    deny,
    kinds,
    receive,
    send,
    turn,
    wait_until,
)
from zeno.agent.audit import read_audit

# --- connecting -----------------------------------------------------------------------


def test_connect_gets_a_ready_frame(make_brain: Any) -> None:
    brain: Brain = make_brain()
    with brain.chat() as ws:
        ready = receive(ws)
    assert ready["type"] == "ready"
    assert ready["session"]
    assert "calculate" in ready["tools"]


@pytest.mark.parametrize("token", ["", "wrong-token"])
def test_a_bad_token_is_refused_at_the_handshake(make_brain: Any, token: str) -> None:
    brain: Brain = make_brain()
    with pytest.raises(WebSocketDisconnect) as refused, brain.chat(token=token):
        pass
    assert refused.value.code == 1008


def test_browser_pages_are_refused_unless_their_origin_is_allowed(make_brain: Any) -> None:
    brain: Brain = make_brain(api_allowed_origins=["http://localhost:3000"])
    with (
        pytest.raises(WebSocketDisconnect) as refused,
        brain.chat(headers={"Origin": "https://evil.example"}),
    ):
        pass
    assert refused.value.code == 1008
    with brain.chat(headers={"Origin": "http://localhost:3000"}) as ws:
        assert receive(ws)["type"] == "ready"


# --- answering ------------------------------------------------------------------------


def test_a_direct_answer(make_brain: Any) -> None:
    brain: Brain = make_brain([final("Hello, Boss.", thought="A greeting.")])
    ws = connect(brain)
    frames = turn(ws, "hi")
    assert frames == [
        {"type": "thought", "turn": "t1", "step": 1, "text": "A greeting."},
        {"type": "text", "turn": "t1", "text": "Hello, Boss."},
        {"type": "done", "turn": "t1", "outcome": "answered", "steps": 1},
    ]


def test_routes_through_memory_and_the_agent_and_streams_every_step(make_brain: Any) -> None:
    brain: Brain = make_brain(
        [act("calculate", thought="Work it out.", expression="2 + 3"), final("It's 5.")]
    )
    brain.run(brain.daemon.services.memory.facts.remember, "Boss likes answers in metric units")
    ws = connect(brain)
    frames = turn(ws, "what is 2 + 3 in metric units?")
    assert kinds(frames) == ["thought", "tool_call", "observation", "thought", "text", "done"]
    assert frames[1] == {
        "type": "tool_call",
        "turn": "t1",
        "step": 1,
        "tool": "calculate",
        "args": {"expression": "2 + 3"},
        "risk": "read_only",
    }
    assert frames[2] == {
        "type": "observation",
        "turn": "t1",
        "step": 1,
        "tool": "calculate",
        "ok": True,
        "content": "5",
    }
    assert frames[-1]["outcome"] == "answered"

    prompt = brain.engine.calls[0][0]
    assert prompt[0].role == "system"
    assert "calculate" in prompt[0].content  # tool instructions
    assert "Boss likes answers in metric units" in prompt[-1].content  # recalled memory
    assert prompt[-1].content.endswith("what is 2 + 3 in metric units?")


def test_the_conversation_carries_over_between_turns(make_brain: Any) -> None:
    brain: Brain = make_brain([final("Nice to meet you, Boss."), final("You are Boss.")])
    ws = connect(brain)
    turn(ws, "I am Boss", turn_id="a")
    turn(ws, "who am I?", turn_id="b")
    second = brain.engine.calls[1][0]
    contents = [m.content for m in second]
    assert "I am Boss" in contents
    assert "Nice to meet you, Boss." in contents


def test_each_connection_is_its_own_conversation(make_brain: Any) -> None:
    brain: Brain = make_brain([final("one"), final("two")])
    turn(connect(brain), "secret from the first window")
    turn(connect(brain), "hello")
    second = brain.engine.calls[1][0]
    assert not any("secret from the first window" in m.content for m in second)


def test_the_displayed_context_reaches_the_prompt_but_not_the_conversation(
    make_brain: Any,
) -> None:
    # The web app sends what is on screen with each message. The model sees it as
    # data for this turn only; the conversation remembers just what was said.
    brain: Brain = make_brain([final("It's 18 degrees."), final("You're welcome.")])
    ws = connect(brain)
    turn(ws, "how warm is it?", turn_id="a", context='{"module":"weather","temp":"18C"}')
    turn(ws, "thanks", turn_id="b")

    first = brain.engine.calls[0][0][-1].content
    assert '{"module":"weather","temp":"18C"}' in first
    assert "data, not instructions" in first
    assert first.endswith("how warm is it?")
    second = [m.content for m in brain.engine.calls[1][0]]
    assert "how warm is it?" in second
    assert not any("18C" in content for content in second)


def test_ui_tools_send_commands_to_the_web_app(make_brain: Any) -> None:
    brain: Brain = make_brain([act("open_module", module="weather"), final("Opened.")])
    frames = turn(connect(brain), "show the weather")
    command = next(f for f in frames if f["type"] == "command")
    assert command == {
        "type": "command",
        "turn": "t1",
        "command": {"type": "open", "module": "weather"},
    }
    assert kinds(frames).index("command") < kinds(frames).index("observation")


def test_a_model_failure_ends_the_turn_with_an_error_outcome(make_brain: Any) -> None:
    brain: Brain = make_brain([])  # the scripted engine has nothing to say
    frames = turn(connect(brain), "hi")
    assert frames[-2]["type"] == "text"
    assert frames[-1]["outcome"] == "error"


# --- approvals ------------------------------------------------------------------------

REMEMBER = act("remember_fact", thought="Worth keeping.", fact="Boss's cat is called Pixel")


def facts(brain: Brain) -> list[str]:
    return [r.text for r in brain.run(brain.daemon.services.memory.facts.all)]


def test_a_mutating_tool_waits_for_approval_over_the_socket(make_brain: Any) -> None:
    brain: Brain = make_brain([REMEMBER, final("I'll remember Pixel.")])
    ws = connect(brain)
    send(ws, type="chat", id="t1", text="my cat is called Pixel")
    frames = []
    while (frame := receive(ws))["type"] != "approval_required":
        frames.append(frame)
    assert kinds(frames) == ["thought", "tool_call"]
    assert frame["tool"] == "remember_fact"
    assert frame["args"] == {"fact": "Boss's cat is called Pixel"}
    assert frame["risk"] == "mutating"
    assert frame["thought"] == "Worth keeping."
    assert frame["description"]
    assert frame["timeout"] == brain.daemon.settings.agent_approval_timeout
    assert facts(brain) == []  # paused: nothing has run

    send(ws, **approve(frame))
    rest = []
    while (frame := receive(ws))["type"] != "done":
        rest.append(frame)
    assert kinds(rest) == ["approval", "observation", "thought", "text"]
    assert rest[0]["approved"] is True
    assert rest[1]["ok"] is True
    assert frame["outcome"] == "answered"
    assert facts(brain) == ["Boss's cat is called Pixel"]


def test_a_denied_tool_never_runs(make_brain: Any) -> None:
    brain: Brain = make_brain([REMEMBER, final("Okay, I won't.")])
    frames = turn(connect(brain), "my cat is called Pixel", decide=deny("not that"))
    observation = next(f for f in frames if f["type"] == "observation")
    assert observation["ok"] is False and "not that" in observation["content"]
    assert facts(brain) == []


def test_no_answer_in_time_is_a_denial(make_brain: Any) -> None:
    brain: Brain = make_brain([REMEMBER, final("Never mind.")], agent_approval_timeout=0.2)
    frames = turn(connect(brain), "my cat is called Pixel")  # nobody answers
    approval = next(f for f in frames if f["type"] == "approval")
    assert approval["approved"] is False and approval["by"] == "timeout"
    assert facts(brain) == []


def test_approvals_are_recorded_in_the_audit_log(make_brain: Any) -> None:
    brain: Brain = make_brain([REMEMBER, final("Done.")])
    turn(connect(brain), "my cat is called Pixel", decide=approve)
    records = read_audit(brain.daemon.settings.audit_log_path)
    decision = next(r for r in records if r.kind == "approval")
    assert decision.data["approved"] is True
    assert decision.data["by"] == "owner"


def test_an_unknown_request_id_is_refused_and_the_turn_keeps_waiting(make_brain: Any) -> None:
    brain: Brain = make_brain([REMEMBER, final("Done.")])
    ws = connect(brain)
    send(ws, type="chat", id="t1", text="remember Pixel")
    while (frame := receive(ws))["type"] != "approval_required":
        pass
    send(ws, type="approval", request_id="not-a-request", approved=True)
    assert receive(ws) == {
        "type": "error",
        "code": "unknown_request",
        "message": "There is no pending approval with that id.",
    }
    send(ws, **approve(frame))
    while (last := receive(ws))["type"] != "done":
        pass
    assert last["outcome"] == "answered"


def test_another_connection_cannot_approve(make_brain: Any) -> None:
    brain: Brain = make_brain([REMEMBER, final("Done.")])
    owner, other = connect(brain), connect(brain)
    send(owner, type="chat", id="t1", text="remember Pixel")
    while (frame := receive(owner))["type"] != "approval_required":
        pass
    send(other, **approve(frame))
    assert receive(other)["code"] == "unknown_request"
    assert facts(brain) == []
    send(owner, **deny()(frame))
    while receive(owner)["type"] != "done":
        pass


def test_one_turn_at_a_time(make_brain: Any) -> None:
    brain: Brain = make_brain([REMEMBER, final("Done.")])
    ws = connect(brain)
    send(ws, type="chat", id="t1", text="remember Pixel")
    while (frame := receive(ws))["type"] != "approval_required":
        pass
    send(ws, type="chat", id="t2", text="and another thing")
    busy = receive(ws)
    assert busy["type"] == "error" and busy["code"] == "busy"
    send(ws, **approve(frame))
    while (last := receive(ws))["type"] != "done":
        pass
    assert last["turn"] == "t1"


def test_cancelling_a_turn_stops_it_before_the_tool_runs(make_brain: Any) -> None:
    brain: Brain = make_brain([REMEMBER, final("Done.")])
    ws = connect(brain)
    send(ws, type="chat", id="t1", text="remember Pixel")
    while receive(ws)["type"] != "approval_required":
        pass
    send(ws, type="cancel", id="t1")
    done = receive(ws)
    assert done == {"type": "done", "turn": "t1", "outcome": "cancelled", "steps": 1}
    assert facts(brain) == []


def test_disconnecting_during_an_approval_cancels_the_run(make_brain: Any) -> None:
    brain: Brain = make_brain([REMEMBER, final("Done.")])
    with brain.chat() as ws:
        receive(ws)
        send(ws, type="chat", id="t1", text="remember Pixel")
        while receive(ws)["type"] != "approval_required":
            pass
    path = brain.daemon.settings.audit_log_path

    def cancelled() -> bool:
        return any(
            r.kind == "run_finished" and r.data["outcome"] == "cancelled" for r in read_audit(path)
        )

    wait_until(cancelled)
    assert facts(brain) == []


# --- bad input ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("not json", "invalid_json"),
        (json.dumps({"type": "launch_missiles"}), "invalid_frame"),
        (json.dumps({"type": "chat", "id": "t1", "text": ""}), "invalid_frame"),
        (json.dumps({"type": "chat", "id": "t1", "text": "hi", "extra": 1}), "invalid_frame"),
        (json.dumps({"type": "chat", "id": "t1", "text": "x" * 5000}), "invalid_frame"),
        (
            json.dumps({"type": "chat", "id": "t1", "text": "hi", "context": "x" * 9000}),
            "invalid_frame",
        ),
        ("x" * 70_000, "frame_too_large"),
    ],
    # Short ids: pytest puts the id in an environment variable, capped at 32767 on Windows.
    ids=["not-json", "unknown-type", "empty", "extra-field", "long-text", "long-context", "huge"],
)
def test_bad_frames_get_an_error_and_the_socket_stays_open(
    make_brain: Any, raw: str, code: str
) -> None:
    brain: Brain = make_brain([final("still here")])
    ws = connect(brain)
    ws.send_text(raw)
    error = receive(ws)
    assert error["type"] == "error" and error["code"] == code
    assert turn(ws, "hi")[-1]["outcome"] == "answered"
