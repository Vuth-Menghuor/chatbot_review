"""Quick integration smoke test for API layer file upload stack."""
import io
import json
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

BASE = "http://localhost:8000/api/v1"


def request(method: str, path: str, token: str | None = None, data: bytes | None = None, content_type: str | None = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"detail": body}
        return exc.code, payload


def multipart_upload(path: str, token: str, filename: str, content: bytes, mime: str):
    boundary = f"----WebKitFormBoundary{uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    email = f"review_{uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    failures = []

    status, reg = request(
        "POST",
        "/auth/register",
        data=json.dumps({"full_name": "Review User", "email": email, "password": password}).encode(),
        content_type="application/json",
    )
    print(f"[register] {status} {reg.get('email', reg)}")
    if status != 201:
        failures.append("register")

    status, login = request(
        "POST",
        "/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        content_type="application/json",
    )
    token = login.get("access_token")
    print(f"[login] {status} token={'yes' if token else 'no'}")
    if status != 200 or not token:
        failures.append("login")
        print("FAILURES:", failures)
        return 1

    status, me = request("GET", "/auth/me", token=token)
    print(f"[auth/me] {status} {me.get('email', me)}")
    if status != 200:
        failures.append("auth/me")

    # Valid 1x1 PNG
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    try:
        status, upload = multipart_upload("/files/upload-image", token, "test.png", png, "image/png")
        print(f"[upload] {status} {upload}")
    except Exception as exc:
        print(f"[upload] ERROR {exc}")
        failures.append("upload")
        upload = {}

    if upload.get("file_id"):
        file_id = upload["file_id"]
        time.sleep(6)
        status, detail = request("GET", f"/files/{file_id}", token=token)
        print(f"[get file] {status} status={detail.get('status')} url={detail.get('public_url')}")
        if status != 200:
            failures.append("get file")
        if detail.get("status") not in {"pending", "processed", "failed"}:
            failures.append("file status")
        if detail.get("status") == "processed":
            print("[worker] processed thumbnail OK")

    status, chat = request(
        "POST",
        "/chat/send",
        token=token,
        data=json.dumps({"message": "integration test hello"}).encode(),
        content_type="application/json",
    )
    print(f"[chat/send] {status} {str(chat)[:200]}")
    if status not in {200, 502, 503}:
        failures.append("chat/send")

    if failures:
        print("FAILURES:", failures)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
