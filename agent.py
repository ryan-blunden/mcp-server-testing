import asyncio
import os
import json
from pathlib import Path
import re
from typing import Mapping
import textwrap
import traceback
from typing import List

import logfire
from pydantic_ai import Agent
from dotenv import load_dotenv
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIModel

MCP_CONFIG_FILE = Path("mcp-config.json")
ENV_SUBS_PATTERN = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
EXIT_COMMANDS = ["exit", "quit", "bye"]
WRAP_WIDTH = 80
SYSTEM_PROMPT = """
You are an advanced problem-solving assistant with access to MCP servers and various tools.
When responding to user requests, you must use an extended thinking process to thoroughly
analyze problems before providing solutions. This helps you arrive at more accurate,
comprehensive, and thoughtful responses.
"""


def wrap_text(text: str) -> str:
    paragraphs = text.split("\n")
    wrapped_paragraphs = [
        textwrap.fill(p, width=WRAP_WIDTH) if p.strip() else p for p in paragraphs
    ]

    return "\n".join(wrapped_paragraphs)


def envsubst(text: str, env: Mapping[str, str]) -> str:
    return ENV_SUBS_PATTERN.sub(lambda m: env.get(m.group(1), m.group(0)), text)


def load_mcp_servers_from_config() -> List[MCPServerStdio]:
    """
    Load MCP server configurations from mcp-config.json which uses the same format as the Claude Desktop app.
    https://modelcontextprotocol.io/quickstart/user#2-add-the-filesystem-mcp-server
    """

    if not MCP_CONFIG_FILE.exists():
        return []

    try:
        with open(MCP_CONFIG_FILE, "r") as f:
            config = json.loads(envsubst(f.read(), os.environ))

        servers = []
        if "mcpServers" not in config:
            return []

        for server_name, server_config in config["mcpServers"].items():
            if "command" not in server_config or "args" not in server_config:
                print(
                    f"Warning: Server '{server_name}' is missing required fields (command, args)."
                )
                continue

            server = MCPServerStdio(
                command=server_config["command"],
                args=server_config["args"],
                env=server_config.get("env", None),
            )
            servers.append(server)
            print(f"Loaded MCP server configuration: {server_name}")

        return servers
    except Exception as e:
        print(f"Error loading MCP server configurations: {e}")
        traceback.print_exc()
        return []


def initialize_agent():
    load_dotenv()

    if os.getenv("LOGFIRE_TOKEN"):
        logfire.configure(token=os.getenv("LOGFIRE_TOKEN"), scrubbing=False)
        logfire.instrument_pydantic_ai()

    try:
        mcp_servers = load_mcp_servers_from_config()
        openai_model = OpenAIModel(os.getenv("OPENAI_MODEL", "o4-mini"))
        agent = Agent(
            name="MCP Agent",
            model=openai_model,
            mcp_servers=mcp_servers,
            instructions=SYSTEM_PROMPT,
        )

        return agent, True
    except Exception as e:
        print(f"Error initializing agent: {e}")
        traceback.print_exc()
        return None, False


async def chat(agent: Agent):
    print(f"\nType one of {EXIT_COMMANDS} to exit, or press Ctrl+C at any time.\n")

    message_history = []

    async with agent.run_mcp_servers():
        print("\n🤖 How can I help you today?")

        while True:
            user_input = input("💬 ")
            print()

            if user_input.lower() in EXIT_COMMANDS:
                print("\nThanks for chatting!")
                break

            try:
                result = await agent.run(user_input, message_history=message_history)
                response = result.output

                wrapped_response = wrap_text(response)
                print(f"\nAgent:\n{wrapped_response}\n")

                message_history = result.all_messages()
            except Exception as e:
                error_msg = f"\nError: {e}"
                print(wrap_text(error_msg))
                traceback.print_exc()
                print(wrap_text("Continuing conversation despite error...\n"))


async def main():
    agent, success = initialize_agent()

    if success and agent:
        # Small delay to allow Logfire to initialize
        await asyncio.sleep(1)
        await chat(agent)
    else:
        print("Agent initialization failed.")


if __name__ == "__main__":
    print("\nStarting Agent CLI...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting due to keyboard interrupt (Ctrl+C)")
        exit_msg = "See you next time!"
        print(wrap_text(exit_msg))
        # Exit with a clean exit code
        exit(0)
    except Exception as e:
        print(f"Unhandled exception: {e}")
        traceback.print_exc()
        exit(1)
