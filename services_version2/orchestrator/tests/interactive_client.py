import urllib.request
import urllib.error
import json
import sys
import uuid

URL = "http://127.0.0.1:8001/chat"

def send_chat_query(question: str, session_id: str):
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
        return None, f"Connection Error: {str(e)}\nMake sure your orchestrator is running on {URL}"

def main():
    session_id = f"cli_{uuid.uuid4().hex[:8]}"
    print("=" * 80)
    print("      GDCE Chatbot Orchestrator Interactive Terminal Client")
    print("=" * 80)
    print(f"Target URL: {URL}")
    print(f"Session ID: {session_id} (maintains multi-turn context)")
    print("Commands: '/exit' or 'exit' to quit. '/reset' to start a new session context.")
    print("-" * 80)

    while True:
        try:
            user_input = input("\nYou > ")
            if not user_input.strip():
                continue
            
            if user_input.strip().lower() in ["/exit", "exit", "quit"]:
                print("Goodbye!")
                break
                
            if user_input.strip().lower() == "/reset":
                session_id = f"cli_{uuid.uuid4().hex[:8]}"
                print(f"[System] Session reset. New Session ID: {session_id}")
                continue

            print("Sending request...")
            response, error = send_chat_query(user_input, session_id)

            if error:
                print(f"\n[ERROR] {error}")
                continue

            # Print main answer
            answer = response.get("answer", "No answer field returned.")
            intent = response.get("intent", "unknown")
            status = response.get("status", "unknown")
            
            print(f"\nAssistant:\n{answer}\n")
            print("-" * 80)
            
            # Print routing & rewrite metadata
            meta = response.get("metadata", {})
            service_query = meta.get("service_query")
            query_strategy = meta.get("query_strategy")
            latency = meta.get("latency_ms", 0.0)
            
            print(f"[Metadata] Intent: {intent.upper()} | Status: {status.upper()} | Latency: {latency:.1f}ms")
            if service_query and service_query != user_input:
                print(f"[Rewrite]  Routed Query: \"{service_query}\"")
                print(f"[Rewrite]  Strategy:     {query_strategy}")
            
            # Print documents/sources if available
            sources = response.get("sources", [])
            if sources:
                print("[Sources]")
                for src in sources[:3]:
                    src_id = src.get("id") or src.get("title") or "doc"
                    score = src.get("score")
                    score_str = f" (Score: {score:.2f})" if score is not None else ""
                    print(f"  - {src_id}{score_str}")
            print("-" * 80)

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\n[ERROR] Unexpected error: {e}")

if __name__ == "__main__":
    main()
