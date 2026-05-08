"""
AGOS — Agent Runtime
Process manager that starts agents, connects to the Go daemon, and handles lifecycle.
"""

import asyncio
import json
import logging
import signal
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agos.runtime")


async def main():
    """Main entry point for the AGOS Python agent runtime."""
    from agents.base import AgentConfig
    from agents.orchestrator import Orchestrator
    from agents.system_agent import SystemAgent

    logger.info("╔══════════════════════════════════════════╗")
    logger.info("║     AGOS Agent Runtime                    ║")
    logger.info("╚══════════════════════════════════════════╝")

    # --- Initialize Orchestrator (Auto-registers all 8 agents) ---
    orchestrator = Orchestrator()
    logger.info(f"Registered {len(orchestrator.sub_agents)} agents")

    # --- Interactive Loop ---
    logger.info("Ready. Type a command (or 'quit' to exit):")
    
    loop = asyncio.get_event_loop()

    while True:
        try:
            user_input = await loop.run_in_executor(None, lambda: input("\n🤖 AGOS > "))
            
            if user_input.strip().lower() in ("quit", "exit", "q"):
                logger.info("Shutting down...")
                break

            if not user_input.strip():
                continue

            # Execute via orchestrator
            result = await orchestrator.execute(user_input.strip())
            
            print(f"\n{'='*60}")
            if result.success:
                print(f"✅ Result:")
                for line in result.output.split("\n"):
                    if line.strip():
                        print(f"   {line[:200]}")
            else:
                print(f"❌ Error: {result.error}")
                if result.output:
                    print(f"   {result.output[:300]}")

            if result.tool_calls:
                print(f"\n🔧 Tool calls: {len(result.tool_calls)}")
                for tc in result.tool_calls:
                    status = "✅" if "result" in tc else "❌"
                    detail = str(tc.get('result', tc.get('error', '?')))
                    if len(detail) > 150:
                        detail = detail[:150] + "..."
                    print(f"   {status} {tc.get('tool', '?')}: {detail}")

            print(f"📊 Tokens: {result.tokens_used}")
            print(f"{'='*60}")


        except (KeyboardInterrupt, EOFError):
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
