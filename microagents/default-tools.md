---
# This is a repo microagent that is always activated
# to include necessary default tools implemented with MCP
name: default-tools
type: repo
version: 1.0.0
agent: CodeActAgent
# mcp_tools:
#   stdio_servers:
# #     # - name: "fetch"
# #     #   command: "uvx"
# #     #   args: ["mcp-server-fetch"]
#     - name: "sequential-thinking"
#       command: "npx"
#       args: ["-y", "@modelcontextprotocol/server-sequential-thinking"]
# We leave the body empty because MCP tools will automatically add the
# tool description for LLMs in tool calls, so there's no need to add extra descriptions.
---
