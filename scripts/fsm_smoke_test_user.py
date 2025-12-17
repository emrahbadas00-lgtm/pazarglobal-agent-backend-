import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load env BEFORE importing workflow so OPENAI_API_KEY is present
def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


load_env(ROOT / ".env")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow import run_workflow, WorkflowInput

USER_ID = "3ec55e9d-93e8-40c5-8e0e-7dc933da997f"
USER_NAME = "emrah badas"
USER_PHONE = "+905412879705"
MEDIA_URLS = [u.strip() for u in os.getenv("MEDIA_URL", "").split(",") if u.strip()]
MEDIA_TYPE = os.getenv("MEDIA_TYPE", "image/jpeg") if MEDIA_URLS else None


def fmt(msg: str, res: dict) -> str:
    resp = res.get("response") or ""
    return f"\n>>> {msg}\nintent: {res.get('intent')}\nsuccess: {res.get('success')}\nresp: {resp[:400]}"


async def step(msg: str):
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
    print(fmt(msg, res))
    return res


async def main():
    load_env(Path(__file__).resolve().parent.parent / ".env")
    await step("iphone 13 satıyorum 25 bin tl")
    await step("fiyatı 27000 yap")
    await step("onayla")


if __name__ == "__main__":
    asyncio.run(main())
