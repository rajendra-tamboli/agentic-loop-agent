import argparse
import asyncio
import json
import os
from datetime import datetime

from dotenv import load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    query,
)

load_dotenv()

DEFAULT_PROMPT = "Review utils.py for bugs that would cause crashes. Fix any issues you find."
TEST_PROMPT = "Write pytest unit tests for utils.py, run them, and fix any failures."

SYSTEM_PROMPT = "You are a senior Python developer. Follow PEP 8."

LOG_FILE = "agent.log"
BLOCKED_SUBSTRING = "rm -rf"


def build_model_options():
    """Return (model, env) for ClaudeAgentOptions based on configured credentials.

    If AZURE_FOUNDRY_ENDPOINT/AZURE_FOUNDRY_API_KEY are set, the Azure AI
    Foundry deployment is addressed as a plain Anthropic-compatible endpoint
    (ANTHROPIC_BASE_URL + ANTHROPIC_API_KEY), not via the SDK's native
    CLAUDE_CODE_USE_FOUNDRY integration, which requires an Azure credential
    chain (az login / Entra ID) instead of a simple key + endpoint.
    Otherwise, falls back to the plain ANTHROPIC_API_KEY already in the
    environment.
    """
    azure_endpoint = os.environ.get("AZURE_FOUNDRY_ENDPOINT")
    azure_api_key = os.environ.get("AZURE_FOUNDRY_API_KEY")
    azure_model = os.environ.get("AZURE_FOUNDRY_MODEL")

    if azure_endpoint and azure_api_key:
        return azure_model, {
            "ANTHROPIC_BASE_URL": azure_endpoint,
            "ANTHROPIC_API_KEY": azure_api_key,
        }

    return None, {}


async def log_and_guard_tool_use(input_data, tool_use_id, context):
    """PreToolUse hook: logs every tool call and blocks destructive Bash commands."""
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now().isoformat()} | {tool_name} | {json.dumps(tool_input)}\n")

    if tool_name == "Bash" and BLOCKED_SUBSTRING in tool_input.get("command", ""):
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Blocked command containing '{BLOCKED_SUBSTRING}'.",
            }
        }

    return {}


async def main():
    parser = argparse.ArgumentParser(description="Sample agentic loop using the Claude Agent SDK.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Prompt to send to the agent. Defaults to a bug-fixing prompt "
        "(or the test-writing prompt when --with-tests is set).",
    )
    parser.add_argument(
        "--with-tests",
        action="store_true",
        help="Allow Bash and use a prompt that writes and runs pytest tests for utils.py.",
    )
    args = parser.parse_args()

    allowed_tools = ["Read", "Edit", "Glob"]
    if args.with_tests:
        allowed_tools.append("Bash")

    if args.prompt is not None:
        prompt = args.prompt
    elif args.with_tests:
        prompt = TEST_PROMPT
    else:
        prompt = DEFAULT_PROMPT

    model, model_env = build_model_options()

    options = ClaudeAgentOptions(
        allowed_tools=allowed_tools,
        permission_mode="acceptEdits",
        system_prompt=SYSTEM_PROMPT,
        hooks={"PreToolUse": [HookMatcher(hooks=[log_and_guard_tool_use])]},
        model=model,
        env=model_env,
    )

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text"):
                    print(block.text)
                elif hasattr(block, "name"):
                    print(f"Tool: {block.name}")
        elif isinstance(message, ResultMessage):
            print(f"Done: {message.subtype}")
            if message.num_turns is not None:
                print(f"Turns: {message.num_turns}")
            if message.total_cost_usd is not None:
                print(f"Cost: ${message.total_cost_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
