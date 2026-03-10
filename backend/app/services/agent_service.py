import time
from typing import List, Optional
import json
import ast
import operator as op
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import Tool, tool
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.config import get_settings
from app.core.logging import logger
from app.services.rag_service import _get_llm

settings = get_settings()

# Define Custom Tools
@tool
def calculator(expression: str) -> str:
    """Useful for when you need to answer questions about math."""
    try:
        return str(_safe_eval(expression))
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"


_SAFE_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.Mod: op.mod,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
    ast.FloorDiv: op.floordiv,
}


def _safe_eval(expression: str) -> float:
    parsed = ast.parse(expression, mode="eval")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPERATORS:
            return _SAFE_OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPERATORS:
            return _SAFE_OPERATORS[type(node.op)](_eval(node.operand))
        raise ValueError("Unsupported expression")

    return _eval(parsed)

@tool
def get_current_weather(location: str) -> str:
    """Get the weather for a location."""
    # Mock weather tool
    return f"The weather in {location} is 72 degrees and sunny."

class AgentService:
    def __init__(self):
        self.llm = _get_llm()
        self.available_tools = {
            "calculator": calculator,
            "weather": get_current_weather
        }
        allowlist = [v.strip() for v in (settings.AGENT_TOOL_ALLOWLIST or "").split(",") if v.strip()]
        self.global_tool_allowlist = set(allowlist) if allowlist else set(self.available_tools.keys())
        logger.info("agent_service_initialized", extra={
            "available_tools": list(self.available_tools.keys()),
            "global_tool_allowlist": sorted(self.global_tool_allowlist),
            "llm_provider": settings.LLM_PROVIDER,
        })

    def _resolve_allowed_tools(self, requested_tools: Optional[List[str]]) -> List[str]:
        requested = list(requested_tools or [])
        denied = [name for name in requested if name not in self.global_tool_allowlist]
        if denied:
            logger.warning("agent_tools_blocked_by_allowlist", extra={"requested": requested, "blocked": denied})
        allowed = [
            name for name in requested
            if name in self.global_tool_allowlist and name in self.available_tools
        ]
        unknown = [name for name in requested if name not in self.available_tools]
        if unknown:
            logger.warning("agent_tools_unknown", extra={"requested": requested, "unknown": unknown})
        return allowed

    def _invoke_tool(self, tool_name: str, argument: str):
        logger.info("agent_tool_call_started", extra={
            "tool_name": tool_name,
            "argument_preview": (argument or "")[:120],
        })
        try:
            result = self.available_tools[tool_name].invoke(argument)
            logger.info("agent_tool_call_succeeded", extra={
                "tool_name": tool_name,
                "result_preview": str(result)[:200],
            })
            return result
        except Exception as exc:
            logger.warning("agent_tool_call_failed", extra={
                "tool_name": tool_name,
                "error": str(exc),
                "error_type": type(exc).__name__,
            })
            return (
                f"I could not run tool '{tool_name}' right now. "
                "I can still help using available knowledge."
            )

    async def run_agent(self, input_text: str, tools_list: List[str], prompt_template: str = "You are a helpful assistant"):
        start = time.perf_counter()
        allowed_tools = self._resolve_allowed_tools(tools_list)
        logger.info("agent_run_started", extra={
            "requested_tools": tools_list,
            "allowed_tools": allowed_tools,
            "input_length": len(input_text)
        })

        try:
            # For Gemini, use a simpler approach since it doesn't support OpenAI function calling
            if settings.LLM_PROVIDER == "gemini":
                output = await self._run_gemini_agent(input_text, allowed_tools, prompt_template)
            else:
                output = await self._run_openai_agent(input_text, allowed_tools, prompt_template)

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info("agent_run_completed", extra={
                "requested_tools": tools_list,
                "allowed_tools": allowed_tools,
                "input_length": len(input_text),
                "output_length": len(output),
                "duration_ms": duration_ms,
            })
            return output
        except Exception as e:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("agent_run_failed", extra={
                "requested_tools": tools_list,
                "allowed_tools": allowed_tools,
                "input_length": len(input_text),
                "duration_ms": duration_ms,
                "error": str(e),
            })
            raise

    async def _run_gemini_agent(self, input_text: str, tools_list: List[str], prompt_template: str) -> str:
        """Use Gemini with a direct prompt approach for tool usage."""
        # Build tool context
        tool_descriptions = []
        for t_name in tools_list:
            if t_name in self.available_tools:
                t = self.available_tools[t_name]
                tool_descriptions.append(f"- {t.name}: {t.description}")

        tool_context = ""
        if tool_descriptions:
            tool_context = "\n\nYou have access to these tools:\n" + "\n".join(tool_descriptions)
            tool_context += "\n\nIf a user asks something that requires a tool, use it by responding with TOOL_CALL: tool_name(argument). Otherwise, answer directly."

        messages = [
            ("system", prompt_template + tool_context),
            ("human", input_text),
        ]
        
        response = await self.llm.ainvoke(messages)
        result = response.content

        # Check if the model wants to use a tool
        if "TOOL_CALL:" in result:
            tool_call = result.split("TOOL_CALL:")[1].strip()
            tool_name = tool_call.split("(")[0].strip()
            tool_arg = tool_call.split("(")[1].rstrip(")").strip().strip('"').strip("'")
            
            if tool_name in tools_list and tool_name in self.available_tools:
                tool_result = self._invoke_tool(tool_name, tool_arg)
                # Feed result back to LLM
                messages.append(("assistant", result))
                messages.append(("human", f"Tool result: {tool_result}. Please provide a natural language answer."))
                final_response = await self.llm.ainvoke(messages)
                result = final_response.content
            else:
                logger.warning("agent_tool_call_blocked", extra={
                    "tool_name": tool_name,
                    "allowed_tools": tools_list,
                })
                result = (
                    "I cannot execute that tool in this workspace. "
                    "Please use one of the enabled tools or ask a direct question."
                )

        return result

    async def _run_openai_agent(self, input_text: str, tools_list: List[str], prompt_template: str) -> str:
        """Use OpenAI function calling agent."""
        from langchain_openai import ChatOpenAI

        tools = []
        for t_name in tools_list:
            if t_name in self.available_tools:
                base_tool = self.available_tools[t_name]
                tools.append(
                    Tool(
                        name=t_name,
                        description=base_tool.description,
                        func=lambda arg, n=t_name: self._invoke_tool(n, arg),
                    )
                )

        prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_template),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        openai_llm = ChatOpenAI(
            openai_api_key=settings.OPENAI_API_KEY,
            model="gpt-4o-mini",
            temperature=0,
        )
        agent = create_openai_functions_agent(openai_llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        response = await agent_executor.ainvoke({"input": input_text})
        return response["output"]

agent_service = AgentService()
