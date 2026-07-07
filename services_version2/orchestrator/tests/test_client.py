import urllib.request
import json
import sys

URL = "http://127.0.0.1:8001/chat"

# Various test questions mapping to different system intents
TEST_CASES = [
    {
        "intent_type": "Small Talk",
        "question": "Hello, who are you and what can you help me with?"
    },
    {
        "intent_type": "General",
        "question": "What is ATIGA?"
    },
    {
        "intent_type": "Calculation",
        "question": "Calculate the duty and tax rates for importing Pure-bred breeding animals valued at $5000 USD."
    },
    {
        "intent_type": "HS Code Lookup",
        "question": "BMW m8 competition"
    },
    {
        "intent_type": "Trade Query",
        "question": "Show me the import statistics and trade volume for the year 2025."
    }
]

def send_chat_query(question: str, session_id: str = "local_test_session"):
    payload = {
        "question": question,
        "session_id": session_id
    }
    data = json.dumps(payload).encode('utf-8')
    
    req = urllib.request.Request(
        URL,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            return response_data, None
    except urllib.error.HTTPError as e:
        try:
            err_data = json.loads(e.read().decode('utf-8'))
            return None, f"HTTP Error {e.code}: {json.dumps(err_data, indent=2)}"
        except Exception:
            return None, f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        return None, f"Connection/System Error: {str(e)}"

def main():
    print("=" * 70)
    print(" GDCE Chatbot Orchestrator Local Integration Test")
    print("=" * 70)
    
    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n[Test Case {i}] Intent Category: {case['intent_type']}")
        print(f"  Query: \"{case['question']}\"")
        print("  Sending request...")
        
        res, err = send_chat_query(case['question'])
        
        if err:
            print(f"  ❌ Error: {err}")
        else:
            print("  ✅ Success Response:")
            # Pretty print the response keys/content nicely
            if "response" in res:
                print(f"    Answer: {res['response']}")
            elif "answer" in res:
                print(f"    Answer: {res['answer']}")
            else:
                print(json.dumps(res, indent=4))
        print("-" * 70)

if __name__ == "__main__":
    main()
