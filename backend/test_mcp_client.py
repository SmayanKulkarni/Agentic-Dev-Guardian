import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    # Simulate an IDE connecting to the 'guardian serve' command
    # We must pass the current PATH so it finds 'guardian' in the venv
    env = os.environ.copy()
    
    server_params = StdioServerParameters(
        command="guardian",
        args=["serve"],
        env=env
    )
    
    print("🚀 Connecting to Guardian MCP Server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ Initialized connection")
            
            # 1. List Resources
            resources = await session.list_resources()
            res_names = [r.name for r in resources.resources]
            print(f"📦 Available Resources: {res_names}")
            
            # 2. List Prompts
            prompts = await session.list_prompts()
            prompt_names = [p.name for p in prompts.prompts]
            print(f"💬 Available Prompts: {prompt_names}")
            
            # 3. List Tools
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"🛠️  Available Tools: {tool_names}")
            
            # 4. Invoke a Resource
            if "guardian://status" in res_names:
                print("\n📡 Fetching Resource: guardian://status")
                status = await session.read_resource("guardian://status")
                if status.contents:
                    print(status.contents[0].text)

            # 5. Invoke a Tool
            print("\n🔍 Calling Tool: query_guardian_graph")
            result = await session.call_tool(
                "query_guardian_graph", 
                {"query": "GatekeeperAgent", "clearance": 0, "top_k": 1}
            )
            print("Tool output snippet:")
            print(result.content[0].text[:500] + "...\n")
            
            print("🎉 All MCP integrations verified successfully!")

if __name__ == "__main__":
    asyncio.run(main())
