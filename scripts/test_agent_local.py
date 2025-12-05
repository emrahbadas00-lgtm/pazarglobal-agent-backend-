"""Local test script for the Pazarglobal Agent Backend.

Sends a sample WhatsApp-style message (defaults to "araba varmı") to the
`/agent/run` endpoint so we can validate the agent workflow and tool
invocations without needing the WhatsApp bridge.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call the local Agent Backend API")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/agent/run",
        help="Agent Backend endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--user-id",
        default="local-test-user",
        help="User ID to send with the request",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="araba varmı",
        help="Message to send to the agent",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load env vars (OPENAI_API_KEY, SUPABASE keys, etc.) so the backend
    # has everything it needs when running locally.
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    payload = {
        "user_id": args.user_id,
        "message": args.message,
        "conversation_history": [],
    }

    print(f"POST {args.url}\nPayload: {json.dumps(payload, ensure_ascii=False)}")

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(args.url, json=payload)
        print(f"Status: {response.status_code}")
        print("Response:")
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}")


if __name__ == "__main__":
    main()
