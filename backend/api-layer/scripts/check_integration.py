"""Development smoke test for API Layer -> orchestrator integration."""

import json
import time

import httpx

BASE_URL = "http://localhost:8000/api/v1"


def main() -> None:
    email = f"integration.{int(time.time())}@example.com"
    with httpx.Client(timeout=90) as client:
        health = client.get(f"{BASE_URL}/health")
        health.raise_for_status()
        assert health.json()["main_chatbot_service"] == "ok"

        client.post(f"{BASE_URL}/auth/register", json={
            "full_name": "Integration Check",
            "email": email,
            "password": "password123",
        }).raise_for_status()
        login = client.post(f"{BASE_URL}/auth/login", json={
            "email": email,
            "password": "password123",
        })
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        sent = client.post(f"{BASE_URL}/chat/send", headers=headers, json={"message": "Hello"})
        sent.raise_for_status()
        chat_id = sent.json()["chat_id"]

        event_types: list[str] = []
        answer = ""
        with client.stream("POST", f"{BASE_URL}/chat/stream", headers=headers, json={
            "chat_id": chat_id,
            "message": "Hello again",
        }) as response:
            response.raise_for_status()
            current_event = "message"
            for line in response.iter_lines():
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                    event_types.append(current_event)
                elif line.startswith("data:") and current_event == "token":
                    answer += json.loads(line.split(":", 1)[1].strip())["content"]

        assert "start" in event_types and "token" in event_types and "done" in event_types
        assert answer
        history = client.get(f"{BASE_URL}/chat/history", headers=headers, params={"chat_id": chat_id})
        history.raise_for_status()
        message_count = len(history.json()["messages"])
        assert message_count >= 4, f"Expected at least four history messages, got {message_count}"
        print("Integration check passed: health, auth, send, SSE stream, and history")


if __name__ == "__main__":
    main()
