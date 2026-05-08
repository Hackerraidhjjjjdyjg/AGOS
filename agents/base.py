# AGOS — Python Agent Runtime
"""
BaseAgent — Abstract base class for all AGOS agents.
Implements the Sense → Think → Act lifecycle with LLM abstraction.
"""

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("agos.agents")


@dataclass
class AgentConfig:
    """Configuration for an agent instance."""
    name: str
    model: str = "llama-3.1-8b-instant"
    priority: int = 2
    token_budget: int = 4096
    capabilities: list[str] = field(default_factory=list)
    groq_api_key: str = ""
    groq_url: str = "https://api.groq.com/openai/v1/chat/completions"
    grpc_host: str = "localhost"
    grpc_port: int = 50051


@dataclass
class TaskResult:
    """Result of an agent task execution."""
    success: bool
    output: str
    tool_calls: list[dict] = field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    agent_uuid: str = ""
    ttft_ms: int = 0
    itl_ms: int = 0
    total_latency_ms: int = 0
    error: Optional[str] = None


class BaseAgent(ABC):
    """
    Abstract base class for all AGOS agents.
    
    Lifecycle: init → sense → think → act → report
    
    Subclasses must implement:
    - sense(): Gather context from the environment
    - think(): Reason about the task using LLM
    - act(): Execute tool calls based on reasoning
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.agent_id: Optional[int] = None
        self.logger = logging.getLogger(f"agos.agent.{config.name}")
        self._running = False
        self._tokens_used = 0
        self._ttft = 0
        self._itl = 0
        self._total_latency = 0

    async def execute(self, task: str, agent_uuid: str = "unknown") -> TaskResult:
        """Execute the ReAct lifecycle: Think → Act → Observe → Think... until done."""
        self.logger.info(f"[{self.config.name}] Executing: {task} | UUID: {agent_uuid}")
        self._running = True
        self.agent_uuid = agent_uuid
        self._tokens_used = 0
        self._ttft = 0
        self._itl = 0
        self._total_latency = 0
        
        try:
            # ── FAST PATH: quick_think matches a direct command ──
            quick_plan = self.quick_think(task)
            if quick_plan:
                self.logger.info(f"[{self.config.name}] Quick think matched!")
                result = await self.act(quick_plan)
                result.ttft_ms = 1 # Fast-path latency
                return result

            # ── SLOW PATH: Full ReAct reasoning loop ──
            history = []
            all_tool_calls = []
            # PRINCIPAL ENGINEERING: Hard limit on agent loop iterations (Section 32)
            max_steps = 10  
            last_good_output = ""

            for step_num in range(max_steps):
                context = await self.sense(task)
                prompt = f"Goal: {task}\nStep: {step_num + 1}/{max_steps}\nContext: {context}\nHistory: {json.dumps(history[-3:])}"
                llm_response = await self.call_llm(prompt)
                
                if not llm_response:
                    break

                # Parse LLM response
                try:
                    plan = json.loads(llm_response)
                except json.JSONDecodeError:
                    # Non-JSON = the LLM gave a direct answer
                    return TaskResult(success=True, output=llm_response, tool_calls=all_tool_calls, tokens_used=self._tokens_used)

                history.append({"step": step_num + 1, "thought": plan.get("thought", "")})

                # If final answer provided, we are done
                if "final_answer" in plan and plan["final_answer"]:
                    return TaskResult(success=True, output=plan["final_answer"], tool_calls=all_tool_calls, tokens_used=self._tokens_used)

                # Execute tool calls
                if plan.get("steps"):
                    result = await self.act(plan)
                    all_tool_calls.extend(result.tool_calls)
                    history[-1]["observation"] = result.output[:1000]
                    if result.output and len(result.output) > 20:
                        last_good_output = result.output

            # ── SYNTHESIS: Final attempt to get a human-readable answer ──
            if last_good_output or history:
                synth_prompt = f"Goal: {task}\nData: {last_good_output or context}\nHistory: {json.dumps(history)}\n\nProvide a definitive, human-readable final answer based on the data above. Do not include internal JSON or thoughts."
                summary = await self.call_llm(synth_prompt, system="You are an expert synthesizer. Provide only the final answer.")
                if summary:
                    return self._create_result(True, summary, all_tool_calls)

            return self._create_result(bool(last_good_output), last_good_output or "No definitive results found.", all_tool_calls)

        except Exception as e:
            self.logger.error(f"[{self.config.name}] Failed: {e}")
            return TaskResult(success=False, output="", error=str(e), tokens_used=self._tokens_used)
        finally:
            self._running = False

    def _create_result(self, success: bool, output: str, tool_calls: list, error: str = None) -> TaskResult:
        """Create a TaskResult with calculated cost and identification."""
        # Cost math from V4 Spec (Section 1): H100 @ $2.10/hr, 800 tok/s -> $0.00073 / 1K tokens
        cost = (self._tokens_used / 1000.0) * 0.00073
        return TaskResult(
            success=success,
            output=output,
            tool_calls=tool_calls,
            tokens_used=self._tokens_used,
            cost_usd=round(cost, 6),
            agent_uuid=self.agent_uuid,
            ttft_ms=self._ttft,
            itl_ms=self._itl,
            total_latency_ms=self._total_latency,
            error=error
        )

    @abstractmethod
    def quick_think(self, task: str) -> Optional[dict]:
        """Optional fast-path for direct command parsing (no LLM)."""
        ...

    @abstractmethod
    async def sense(self, task: str) -> str:
        """Gather context from the environment relevant to the task."""
        ...

    async def think(self, task: str, context: str) -> dict:
        """DEPRECATED: Subclasses now use the ReAct loop in execute()."""
        return {"steps": []}

    @abstractmethod
    async def act(self, plan: dict) -> TaskResult:
        """Execute the plan by making tool calls."""
        ...

    async def call_llm(self, prompt: str, system: str = "") -> str:
        """Call the LLM via Groq API for ultra-fast inference."""
        api_key = self.config.groq_api_key or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            self.logger.error("GROQ_API_KEY not set — cannot call LLM")
            return ""

        try:
            import httpx
            import time
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system or self._default_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": self.config.token_budget,
                "stream": True, # Mandatory for TTFT/ITL
            }

            start_time = time.perf_counter()
            first_token_time = None
            content_chunks = []
            
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream("POST", self.config.groq_url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not first_token_time:
                            first_token_time = time.perf_counter()
                            self._ttft = int((first_token_time - start_time) * 1000)
                        
                        if line.startswith("data: "):
                            if "[DONE]" in line:
                                break
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk["choices"][0].get("delta", {}).get("content", "")
                                if delta:
                                    content_chunks.append(delta)
                            except:
                                pass
            
            end_time = time.perf_counter()
            full_content = "".join(content_chunks)
            self._total_latency = int((end_time - start_time) * 1000)
            
            # Simplified ITL calculation
            token_count = len(full_content.split()) # Approximation for ITL
            if token_count > 1:
                self._itl = int((end_time - first_token_time) * 1000 / token_count)
            
            self._tokens_used += int(token_count * 1.3) # Rough multiplier for BPE
            return full_content

        except Exception as e:
            self.logger.error(f"Groq LLM streaming call failed: {e}")
            return ""

    def _default_system_prompt(self) -> str:
        return (
            f"You are {self.config.name}, a core autonomous entity in the AGOS world-class agent fleet. "
            f"Capabilities: {', '.join(self.config.capabilities)}. "
            "Task Execution Protocol (ReAct):\n"
            "1. Analyze goal and context.\n"
            "2. Decide: Provide 'final_answer' (if task done) OR 'steps' (to gather more data).\n"
            "CRITICAL: Always return a JSON object with 'thought' and either 'steps' or 'final_answer'. "
            "Never leak your 'thought' into 'final_answer'. Use tools recursively until the goal is fully achieved."
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def tokens_used(self) -> int:
        return self._tokens_used
