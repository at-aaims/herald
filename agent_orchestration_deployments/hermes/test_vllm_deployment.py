import os
os.environ['no_proxy'] = 'localhost,127.0.0.1'

import requests
import json

API_URL = "http://localhost:8082/v1/chat/completions"

tools_json = [
    {
        "type": "function",
        "function": {
            "name": "rag_chain",
            "description": "Retrieves information from HPC documentation",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sql_qna_chain",
            "description": "Queries HPC job database for statistics and usage patterns related to HPC jobs, users, science domain.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "job_pred",
            "description": "Predicts resource requirements or utilization of HPC jobs based on input features.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}
        }
    }
]

# Put tools in system message instead of using vLLM's tools parameter
system_content = f"""You are a helpful assistant with access to the following functions:

{json.dumps(tools_json, indent=2)}

To call a function, respond with:
<tool_call>
{{"name": "function_name", "arguments": {{"query": "your query"}}}}
</tool_call>"""

messages = [
    {"role": "system", "content": system_content},
    {
        "role": "user",
        "content": "Find the top 3 science domains in February 2025 with the highest CPU energy consumed in leadership-class jobs, then predict energy for the top domain."
    }
]

response = requests.post(
    API_URL,
    json={
        "model": "Hermes-4-14B-FP8",
        "messages": messages,
        # No "tools" parameter - we put them in system message instead
        "temperature": 0.2,
        "max_tokens": 500
    }
)

print("Status:", response.status_code)
if response.status_code == 200:
    result = response.json()
    content = result['choices'][0]['message']['content']
    print("\nResponse:")
    print(content)
    
    # Check for tool calls
    import re
    tool_calls = re.findall(r'<tool_call>(.*?)</tool_call>', content, re.DOTALL)
    print(f"\nTool calls detected: {len(tool_calls)}")
    for i, call in enumerate(tool_calls, 1):
        print(f"{i}. {call}")
else:
    print("Error:", response.text)