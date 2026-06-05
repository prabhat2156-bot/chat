import asyncio
import logging
from typing import Dict, Optional, Callable, Awaitable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_tasks: Dict[str, asyncio.Task] = {}


def now_utc():
    return datetime.now(timezone.utc)


async def _timeout_worker(
    key: str,
    delay: int,
    callback: Callable[..., Awaitable],
    *args,
    **kwargs,
):
    try:
        await asyncio.sleep(delay)
        if key in _tasks:
            await callback(*args, **kwargs)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Timeout worker error for key {key}: {e}")
    finally:
        _tasks.pop(key, None)


def set_timeout(
    key: str,
    delay: int,
    callback: Callable[..., Awaitable],
    *args,
    **kwargs,
) -> None:
    cancel_timeout(key)
    task = asyncio.create_task(
        _timeout_worker(key, delay, callback, *args, **kwargs)
    )
    _tasks[key] = task


def cancel_timeout(key: str) -> None:
    task = _tasks.pop(key, None)
    if task and not task.done():
        task.cancel()


def cancel_all_for_match(match_id: str) -> None:
    keys_to_cancel = [k for k in list(_tasks.keys()) if match_id in k]
    for key in keys_to_cancel:
        cancel_timeout(key)


def has_timeout(key: str) -> bool:
    return key in _tasks and not _tasks[key].done()
