import asyncio

from app.services.agent_service import AgentService


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _QueueLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    async def ainvoke(self, _messages):
        return _FakeResponse(self._responses.pop(0))


def test_tool_allowlist_blocks_unapproved_tool_calls():
    svc = AgentService()
    svc.global_tool_allowlist = {"weather"}  # calculator blocked
    svc.llm = _QueueLLM(["TOOL_CALL: calculator(2+2)"])

    result = asyncio.run(svc.run_agent("please calculate 2+2", ["calculator"], "You are helpful"))
    assert "cannot execute that tool" in result.lower()


def test_tool_failure_is_graceful_and_auditable():
    svc = AgentService()
    svc.global_tool_allowlist = {"calculator"}
    svc.llm = _QueueLLM([
        "TOOL_CALL: calculator(10/0)",
        "I could not run the calculator, but here is a fallback answer.",
    ])

    class _BrokenTool:
        name = "calculator"
        description = "broken calculator"

        def invoke(self, _arg):
            raise RuntimeError("boom")

    svc.available_tools["calculator"] = _BrokenTool()

    result = asyncio.run(svc.run_agent("do math", ["calculator"], "You are helpful"))
    assert "fallback answer" in result.lower()
