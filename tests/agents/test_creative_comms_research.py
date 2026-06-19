"""Unit tests for Creative/Comms/Research agent parsing + Research pure tools."""

from agents.comms_agent import CommsAgent
from agents.creative_agent import CreativeAgent
from agents.research_agent import ResearchAgent


# ─── Creative ───────────────────────────────────

def test_creative_write():
    plan = CreativeAgent().quick_think("write a poem about spring")
    assert plan["steps"][0]["tool"] == "write_text"
    assert plan["steps"][0]["args"]["topic"] == "a poem about spring"


def test_creative_translate():
    plan = CreativeAgent().quick_think("translate hello to spanish")
    args = plan["steps"][0]["args"]
    assert plan["steps"][0]["tool"] == "translate"
    assert args["text"] == "hello"
    assert args["target_language"] == "spanish"


def test_creative_outline():
    plan = CreativeAgent().quick_think("outline a business plan")
    assert plan["steps"][0]["tool"] == "generate_outline"
    assert plan["steps"][0]["args"]["topic"] == "a business plan"


def test_creative_no_match():
    assert CreativeAgent().quick_think("scan ports") is None


# ─── Comms ───────────────────────────────────

def test_comms_email():
    plan = CommsAgent().quick_think("email John about the meeting")
    assert plan["steps"][0]["tool"] == "draft_email"


def test_comms_schedule():
    plan = CommsAgent().quick_think("schedule a meeting tomorrow")
    assert plan["steps"][0]["tool"] == "schedule_event"


def test_comms_no_match():
    assert CommsAgent().quick_think("compute statistics") is None


# ─── Research ───────────────────────────────────

def test_research_search():
    plan = ResearchAgent().quick_think("search for quantum computing")
    tools = [s["tool"] for s in plan["steps"]]
    assert tools == ["web_search", "summarize"]
    assert plan["steps"][0]["args"]["query"] == "quantum computing"


def test_research_fetch():
    plan = ResearchAgent().quick_think("fetch https://example.com")
    assert plan == {"steps": [{"tool": "fetch_url", "args": {"url": "https://example.com"}}]}


def test_research_no_match():
    assert ResearchAgent().quick_think("hash a file") is None


def test_research_summarize_short_passthrough():
    text = "short text"
    assert ResearchAgent()._summarize(text) == text


def test_research_summarize_long_truncates():
    text = ". ".join(f"sentence number {i} with enough words" for i in range(20)) + "."
    out = ResearchAgent()._summarize(text)
    assert len(out) <= 500
    assert out.startswith("sentence number 0")


def test_research_extract_facts():
    text = "This is a sufficiently long fact about cats. Short. Another long fact about dogs here."
    out = ResearchAgent()._extract_facts(text)
    lines = out.splitlines()
    assert all(line.startswith("•") for line in lines)
    assert any("cats" in line for line in lines)


def test_research_cite_sources():
    out = ResearchAgent()._cite_sources("python", "http://x")
    assert out.startswith("[1] DuckDuckGo search: python")
    assert "http://x" in out
