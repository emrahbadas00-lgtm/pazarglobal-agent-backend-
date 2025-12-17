import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Simple .env loader (key=value lines)
def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if not line or line.strip().startswith('#'):
            continue
        if '=' not in line:
            continue
        key, val = line.split('=', 1)
        os.environ.setdefault(key.strip(), val.strip())


# Load env BEFORE importing workflow so OPENAI_API_KEY is set
load_env(ROOT / ".env")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow import run_workflow, WorkflowInput

def format_result(msg: str, res: dict) -> str:
    resp = res.get("response") or ""
    return (
        f"\n>>> {msg}\n"
        f"intent: {res.get('intent')}\n"
        f"success: {res.get('success')}\n"
        f"response: {resp[:500]}"
    )


async def main():
    load_env(Path(__file__).resolve().parent.parent / ".env")
    user_id = str(uuid.uuid4())
    print(f"user: {user_id}")

    async def step(msg: str):
        res = await run_workflow(
            WorkflowInput(
                input_as_text=msg,
                user_id=user_id,
                user_name="Test User",
                conversation_history=[],
                media_paths=None,
                media_type=None,
            )
        )
        print(format_result(msg, res))
        return res

    await step("iphone 13 satıyorum 25 bin tl")
    await step("fiyatı 27000 yap")
    await step("onayla")


if __name__ == "__main__":
    asyncio.run(main())
