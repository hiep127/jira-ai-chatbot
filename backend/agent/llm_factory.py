from __future__ import annotations

import asyncio

from copilot import CopilotClient
from copilot.generated.session_events import SessionEventType
from copilot.session import PermissionHandler

_DEFAULT_MODEL = "gpt-4o"


async def call_copilot(
    prompt: str,
    model_id: str = "",
    system_prompt: str = "",
) -> str:
    model = model_id if model_id else _DEFAULT_MODEL
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    try:
        async with CopilotClient() as client:
            async with await client.create_session(
                model=model,
                on_permission_request=PermissionHandler.approve_all,
            ) as session:
                done = asyncio.Event()
                parts: list[str] = []

                def on_event(event) -> None:
                    if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
                        parts.append(event.data.delta_content or "")
                    elif event.type == SessionEventType.SESSION_IDLE:
                        done.set()

                session.on(on_event)
                await session.send(full_prompt)
                await asyncio.wait_for(done.wait(), timeout=120)
                return "".join(parts)
    except Exception as e:
        raise RuntimeError(
            f"Copilot SDK session failed — {e}. "
            "Verify 'gh auth login' has been run and the Copilot subscription is active."
        )
