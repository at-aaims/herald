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
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to search for in HPC documentation"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sql_qna_chain",
            "description": "Queries HPC job database for statistics and usage patterns related to HPC jobs, users, science domain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query or question about HPC job statistics"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "job_pred",
            "description": "Predicts resource requirements or utilization of HPC jobs based on input features.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The prediction query with job features"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

messages = [
    {
        "role": "system",
        "content": "You are a helpful HPC assistant with access to documentation search, database queries, and job prediction capabilities."
    },
    {
        "role": "user",
        "content": "Find the top 3 science domains in February 2025 with the highest CPU energy consumed in leadership-class jobs, then predict energy for the top domain."
    }
]

response = requests.post(
    API_URL,
    json={
        "model": "Nemotron-Ultra-253B-FP8",
        "messages": messages,
        "tools": tools_json,
        "tool_choice": "auto",
        "temperature": 0.2,
        "max_tokens": 1000
    }
)

print("Status:", response.status_code)
if response.status_code == 200:
    result = response.json()
    message = result['choices'][0]['message']
    
    print("\nResponse:")
    print(json.dumps(message, indent=2))
    
    # Check for tool calls
    if 'tool_calls' in message and message['tool_calls']:
        print(f"\nTool calls detected: {len(message['tool_calls'])}")
        for i, call in enumerate(message['tool_calls'], 1):
            print(f"\n{i}. Function: {call['function']['name']}")
            print(f"   Arguments: {call['function']['arguments']}")
    elif 'content' in message:
        print(f"\nText response: {message['content']}")
        
        # Also check for JSON tool calls in content
        import re
        tool_calls = re.findall(r'\{[^}]*"name"[^}]*"arguments"[^}]*\}', message['content'])
        if tool_calls:
            print(f"\nJSON tool calls found in content: {len(tool_calls)}")
            for i, call in enumerate(tool_calls, 1):
                print(f"{i}. {call}")
else:
    print("Error:", response.text)
