"""
MCP Client: JIT Tool Loading Smoke Test.

Tests the full JIT lifecycle:
  1. Connect — only 4 bootstrap tools should be visible.
  2. Call list_capabilities() to see available domains.
  3. Call equip_capability("pr_governance") — tools list should grow.
  4. Call evaluate_pr_diff (now available).
  5. Call unequip_capability("pr_governance") — tools list should shrink.
"""

import asyncio
import os
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER_CMD = "guardian"
ENV = {**os.environ, "PATH": os.environ.get("PATH", "") + ":/home/smayan/Desktop/Agentic/backend/.venv/bin"}

SAMPLE_DIFF = """\
diff --git a/app/auth.py b/app/auth.py
--- a/app/auth.py
+++ b/app/auth.py
@@ -1,5 +1,6 @@
+import os
 def get_api_key():
-    return settings.api_key
+    return os.environ["GROQ_API_KEY"]
"""


async def main() -> None:
    params = StdioServerParameters(command=SERVER_CMD, args=["serve"], env=ENV)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ Connected to Guardian MCP Server\n")

            # ── Step 1: Check bootstrap tools only ─────────────────
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"🔧 Bootstrap tools ({len(tool_names)}): {tool_names}")
            assert "evaluate_pr_diff" not in tool_names, "JIT FAIL: evaluate_pr_diff should NOT be loaded yet"
            assert "equip_capability" in tool_names, "equip_capability must be in bootstrap"
            print("   ✅ Only bootstrap tools active — context window is lean!\n")

            # ── Step 2: List capabilities ───────────────────────────
            result = await session.call_tool("list_capabilities", {})
            print("📋 list_capabilities output:")
            print(result.content[0].text[:600])
            print()

            # ── Step 3: Equip pr_governance ─────────────────────────
            equip_result = await session.call_tool("equip_capability", {"domain": "pr_governance"})
            print(f"⚡ equip_capability('pr_governance'): {equip_result.content[0].text}\n")

            tools_after = await session.list_tools()
            tool_names_after = [t.name for t in tools_after.tools]
            print(f"🔧 Tools after equip ({len(tool_names_after)}): {tool_names_after}")
            assert "evaluate_pr_diff" in tool_names_after, "JIT FAIL: evaluate_pr_diff should now be available"
            print("   ✅ evaluate_pr_diff dynamically registered!\n")

            # ── Step 4: Call the newly equipped tool ────────────────
            eval_result = await session.call_tool(
                "evaluate_pr_diff",
                {"diff_content": SAMPLE_DIFF, "repo_path": ".", "clearance": 0},
            )
            snippet = eval_result.content[0].text[:400]
            print(f"🔍 evaluate_pr_diff snippet:\n{snippet}\n")

            # ── Step 5: Unequip pr_governance ───────────────────────
            unequip_result = await session.call_tool("unequip_capability", {"domain": "pr_governance"})
            print(f"🗑️  unequip_capability('pr_governance'): {unequip_result.content[0].text}\n")

            tools_final = await session.list_tools()
            tool_names_final = [t.name for t in tools_final.tools]
            print(f"🔧 Tools after unequip ({len(tool_names_final)}): {tool_names_final}")
            assert "evaluate_pr_diff" not in tool_names_final, "JIT FAIL: evaluate_pr_diff should be unloaded"
            print("   ✅ Context window cleaned up!\n")

            print("🎉 JIT Tool Loading verified end-to-end!")


if __name__ == "__main__":
    asyncio.run(main())
