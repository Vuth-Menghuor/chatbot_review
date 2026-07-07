# pyrefly: ignore [missing-import]
import redis

# Connect to Redis
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

session_id = "your_session_id_here"
stream_key = f"session:{session_id}:transcript"

try:
    # Fetch all entries in the stream
    entries = r.xrange(stream_key)
    print(f"\n--- TRANSCRIPT FOR SESSION: {session_id} ---")
    for entry_id, fields in entries:
        print(f"[{fields.get('ts')}] {fields.get('role').upper()}: {fields.get('content')}")
except Exception as e:
    print(f"Failed to read Redis stream: {e}")
