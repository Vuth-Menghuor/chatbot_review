import os
import sys
import uuid
import json
import urllib.request
import urllib.error
import socket

_LOCK_PORT = 47821  # arbitrary unused local port, just for this client's mutex

def acquire_single_instance_lock() -> socket.socket:
    """
    Prevents a second interactive_client.py from starting while one is
    already running. Binding a local TCP port acts as a mutex: only one
    process can hold it at a time, and the OS releases it automatically
    if this process crashes or is killed — no stale lockfile to clean up.
    """
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # SO_REUSEADDR intentionally omitted — we want a strict single holder.
        lock_socket.bind(("127.0.0.1", _LOCK_PORT))
    except OSError:
        print(
            "Another interactive_client.py is already running "
            "(detected via lock port). Close it before starting a new one.",
            file=sys.stderr,
        )
        sys.exit(1)
    return lock_socket


# Target URL configuration: defaults to localhost:8001 but can be overridden by env vars or CLI args
HOST = os.getenv("ORCHESTRATOR_HOST", "127.0.0.1")
PORT = os.getenv("ORCHESTRATOR_PORT", "8001")
URL = f"http://{HOST}:{PORT}/chat"

if len(sys.argv) > 1:
    arg = sys.argv[1]
    if arg.startswith("http://") or arg.startswith("https://"):
        URL = arg
    else:
        URL = f"http://{arg}/chat"




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

            question = user_input

            print("Sending request...")
            response, error = send_chat_query(question, session_id)

            if error:
                print(f"\n[ERROR] {error}")
                continue

            # Print main answer
            answer = response.get("answer") or response.get("message") or "No answer field returned."
            intent = response.get("intent", "unknown")
            status = response.get("status", "unknown")
            
            # Print assistant response
            print(f"\nAssistant:\n{answer}\n")
            
            # Print clarifications if present in response
            clarifications = response.get("clarifications", [])
            if clarifications:
                print(f"[Clarification Questions]")
                for q in clarifications:
                    print(f"  ❓ {q}")
                print()
            print("-" * 80)
            
            # Print routing & rewrite metadata
            meta = response.get("metadata", {})
            service_query = meta.get("service_query")
            query_strategy = meta.get("query_strategy")
            # latency_ms is a top-level field on the response, not inside metadata
            latency_s = response.get("latency_ms", meta.get("latency_ms", 0.0)) / 1000.0

            print(f"[Metadata] Intent: {intent.upper()} | Status: {status.upper()} | Latency: {latency_s:.3f}s")
            if intent == "out_of_scope":
                print("[Scope]    ⚠️  Query refused: outside system's operational domain.")

            if service_query and service_query != user_input:
                print(f"[Rewrite]  Routed Query: \"{service_query}\"")
                print(f"[Rewrite]  Strategy:     {query_strategy}")

            # Print per-service response times (how long each downstream service took)
            service_latencies = meta.get("service_latencies_s", {})
            if service_latencies:
                parts = "  |  ".join(f"{svc}: {t:.3f}s" for svc, t in service_latencies.items())
                print(f"[Services] {parts}")
            
            # Print documents/sources if available
            sources = response.get("sources", [])
            if sources:
                print("[Sources]")
                for src in sources[:3]:
                    src_id = src.get("id") or src.get("title") or "doc"
                    score = src.get("score")
                    score_str = f" (Score: {score:.2f})" if score is not None else ""
                    print(f"  - {src_id}{score_str}")

            # Print suggestions if available
            suggestions = response.get("suggestion", [])
            if suggestions:
                print(f"\n[Suggestions]")
                for s in suggestions:
                    print(f"  💡 {s}")
            print("-" * 80)

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\n[ERROR] Unexpected error: {e}")

if __name__ == "__main__":
    _lock = acquire_single_instance_lock()  # keep reference alive for the process lifetime
    main()

