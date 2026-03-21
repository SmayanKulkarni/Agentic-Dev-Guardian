import os
from dotenv import load_dotenv

load_dotenv()
print("GROQ_API_KEY:", os.environ.get("GROQ_API_KEY", "")[:5])

from concurrent.futures import ThreadPoolExecutor
from langfuse import observe

@observe()
def call_groq(node_name):
    try:
        from groq import Groq
        client = Groq()
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": f"Message from {node_name}"}],
            model="llama-3.3-70b-versatile",
        )
        print(f"[{node_name}] SUCCESS: {response.choices[0].message.content}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[{node_name}] ERROR: {type(e).__name__} - {e}")

print("Running MoA Concurrent Test with Langfuse Observe...")
with ThreadPoolExecutor(max_workers=2) as executor:
    executor.submit(call_groq, "Gatekeeper")
    executor.submit(call_groq, "RedTeam")
