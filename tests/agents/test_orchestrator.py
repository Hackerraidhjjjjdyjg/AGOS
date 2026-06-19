"""Unit tests for the Orchestrator routing / decomposition logic."""

from agents.orchestrator import Orchestrator


def make_orch():
    return Orchestrator()


def test_registers_all_eight_agents():
    o = make_orch()
    assert set(o.sub_agents) == {
        "system", "research", "code", "creative",
        "data", "security", "comms", "memory",
    }


def test_classify_intent_routing():
    o = make_orch()
    cases = {
        "open safari": "system",
        "search for quantum computing": "research",
        "run python script": "code",
        "write a poem about spring": "creative",
        "query the sales table": "data",
        "scan ports on localhost": "security",
        "email john about lunch": "comms",
        "remember my birthday is may 1": "memory",
    }
    for task, expected in cases.items():
        assert o._classify_intent(task) == expected, task


def test_classify_intent_defaults_to_system():
    o = make_orch()
    assert o._classify_intent("zxcvbnm qwerty") == "system"


def test_clean_input_strips_prompts_and_labels():
    o = make_orch()
    assert o._clean_input("User: open safari") == "open safari"
    assert o._clean_input("Assistant: hello") == "hello"
    assert o._clean_input("🤖 AGOS > open safari") == "open safari"
    assert o._clean_input("plain task") == "plain task"


def test_decompose_single_task():
    o = make_orch()
    assert o._decompose("open safari") == ["open safari"]


def test_decompose_then_chain():
    o = make_orch()
    parts = o._decompose("open safari then set volume to 50")
    assert parts == ["open safari", "set volume to 50"]


def test_decompose_multi_connector():
    o = make_orch()
    parts = o._decompose("search for cats, then write a poem, and finally remember it")
    assert parts == ["search for cats", "write a poem", "remember it"]


def test_list_agents_shape():
    o = make_orch()
    agents = o.list_agents()
    assert len(agents) == 8
    for a in agents:
        assert set(a.keys()) == {"id", "name", "model", "priority", "capabilities", "status"}
        assert a["status"] == "active"
        assert isinstance(a["capabilities"], list)
