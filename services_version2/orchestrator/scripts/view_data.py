import sys
import os
import json
from dotenv import load_dotenv

# Set PYTHONPATH to root of project so imports resolve correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

import redis
from app.infrastructure import SessionLocal
from app.infrastructure.models import (
    ChatSession,
    ChatMessage,
    SessionContextModel,
    IntentRoute,
    ServiceCall,
    ConversationSummary,
    ChatFeedback,
    ChatAttachment,
    FailedRequest,
    ModelUsageLog,
)


def view_redis():
    print("\n" + "=" * 60)
    print(" [REDIS] ACTIVE DATA IN REDIS CACHE ")
    print("=" * 60)
    
    redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD")
    if redis_password == "":
        redis_password = None
    
    try:
        r = redis.Redis(
            host=redis_host, 
            port=redis_port, 
            db=redis_db, 
            password=redis_password,
            decode_responses=True
        )
        r.ping()
    except Exception as e:
        print(f"[-] Failed to connect to Redis at {redis_host}:{redis_port} | Error: {e}")
        return

    context_keys = r.keys("session:*:context")
    print(f"Found {len(context_keys)} active session context(s) in Redis:")
    
    for k in context_keys[:5]:
        sess_id = k.split(":")[1]
        print(f"\n[Session ID]: {sess_id}")
        
        raw_val = r.get(k)
        if raw_val:
            try:
                val = json.loads(raw_val)
                print(f"   • User ID: {val.get('user_id')}")
                print(f"   • Project ID: {val.get('project_id')}")
                print(f"   • Import/Export Mode: {val.get('import_export_mode')}")
                print(f"   • Product Category: {val.get('product_category')}")
                print(f"   • Active turns count: {len(val.get('turns', []))}")
                
                if val.get('turns'):
                    print("   • Last turn context:")
                    last_turn = val['turns'][-1]
                    print(f"       User: {last_turn.get('user_input') or last_turn.get('user', '')}")
                    print(f"       Bot:  {last_turn.get('bot_response') or last_turn.get('bot', '')}")
            except Exception as parse_err:
                print(f"   • Failed to parse context payload: {parse_err}")
        
        # Check Redis Stream transcript
        stream_key = f"session:{sess_id}:transcript"
        try:
            stream_entries = r.xrange(stream_key, count=3)
            if stream_entries:
                print(f"   • Redis Stream transcript entries (last {len(stream_entries)}):")
                for entry_id, fields in stream_entries:
                    print(f"       [{entry_id}] {fields.get('role', 'unknown')}: {fields.get('content', '')[:65]}...")
        except Exception:
            pass

    if len(context_keys) > 5:
        print(f"\n... and {len(context_keys) - 5} more sessions active in Redis.")


def view_postgres():
    print("\n" + "=" * 60)
    print(" [POSTGRES] PERSISTENT DATA IN POSTGRESQL ")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # Table counts
        print("Table Record Counts:")
        tables = [
            ("chat_sessions", ChatSession),
            ("chat_messages", ChatMessage),
            ("session_contexts", SessionContextModel),
            ("intent_routes", IntentRoute),
            ("service_calls", ServiceCall),
            ("conversation_summaries", ConversationSummary),
            ("chat_feedback", ChatFeedback),
            ("chat_attachments", ChatAttachment),
            ("failed_requests", FailedRequest),
            ("model_usage_logs", ModelUsageLog),
        ]
        
        for name, model in tables:
            count = db.query(model).count()
            print(f" [DB] {name:25} : {count} rows")
            
        # Recent sessions
        print("\n[RECENT SESSIONS - Last 3]:")
        sessions = db.query(ChatSession).order_by(ChatSession.created_at.desc()).limit(3).all()
        for s in sessions:
            print(f" • Session: {s.session_id} | User: {s.user_id} | Project: {s.project_id} | Created: {s.created_at}")

        # Recent messages
        print("\n[RECENT CHAT MESSAGES - Last 5]:")
        msgs = db.query(ChatMessage).order_by(ChatMessage.created_at.desc()).limit(5).all()
        for m in msgs:
            print(f" • [{m.created_at}] Session: {m.session_id[:10]}... | {m.role.upper():9} : {m.content[:75]}...")

        # Recent model usage
        print("\n[RECENT MODEL USAGE LOGS - Last 3]:")
        usage = db.query(ModelUsageLog).order_by(ModelUsageLog.created_at.desc()).limit(3).all()
        for u in usage:
            print(f" • Session: {u.session_id[:10]}... | Model: {u.model_name} | Prompt tokens: {u.prompt_tokens} | Completion: {u.completion_tokens} | Total: {u.total_tokens}")

        # Recent failures
        print("\n[RECENT FAILED REQUESTS - Last 3]:")
        fails = db.query(FailedRequest).order_by(FailedRequest.created_at.desc()).limit(3).all()
        for f in fails:
            print(f" • [{f.created_at}] Service: {f.service_name} | Error: {f.error_message}")
            
    except Exception as e:
        print(f"[-] Failed to query PostgreSQL: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    view_redis()
    view_postgres()
