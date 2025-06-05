#!/usr/bin/env just

set shell := ["bash", "-c"]
set positional-arguments := true

inspector:
    npx @modelcontextprotocol/inspector \
      npx -y @ryan.blunden/discord-sdk -- -- mcp start --bot-token npx -y --package @ryan.blunden/discord-sdk -- -- mcp start --bot-token "$(doppler secrets get DISCORD_BOT_TOKEN --plain)"

agent:
    doppler run -- uv run agent.py
