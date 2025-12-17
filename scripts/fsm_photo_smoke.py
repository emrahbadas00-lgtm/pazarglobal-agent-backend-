import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if line and not line.strip().startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow import run_workflow, WorkflowInput

USER_ID = "3ec55e9d-93e8-40c5-8e0e-7dc933da997f"
USER_NAME = "emrah badas"
USER_PHONE = "+905412879705"
MEDIA_URLS = [u.strip() for u in os.getenv("MEDIA_URL", "").split(",") if u.strip()]
MEDIA_TYPE = os.getenv("MEDIA_TYPE", "image/jpeg") if MEDIA_URLS else None

async def main():
    messages = [
        "araba satıyorum 500000 tl",
        "fiyatı 520000 yap",
        "onayla",
    ]
    for msg in messages:
        res = await run_workflow(
            WorkflowInput(
                input_as_text=msg,
                user_id=USER_ID,
                user_name=USER_NAME,
                user_phone=USER_PHONE,
                auth_context={"user_id": USER_ID, "phone": USER_PHONE, "authenticated": True},
                conversation_history=[],
                media_paths=MEDIA_URLS or None,
                media_type=MEDIA_TYPE,
            )
        )
        print(f"\n>>> {msg}")
        print(f"intent: {res.get('intent')} success: {res.get('success')}")
        print(res.get("response"))

if __name__ == "__main__":
    asyncio.run(main())
