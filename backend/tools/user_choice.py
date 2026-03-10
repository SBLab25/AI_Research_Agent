"""
User Choice Mechanism — Async mechanism for presenting choices to the user
and waiting up to 300 seconds for a response.
"""

import asyncio
from typing import Optional

# Global state for pending choices
_pending_choices: dict[str, asyncio.Event] = {}
_choice_results: dict[str, int] = {}


def create_choice(choice_id: str):
    """Create a pending choice that the pipeline will wait on."""
    _pending_choices[choice_id] = asyncio.Event()
    _choice_results.pop(choice_id, None)


def submit_choice(choice_id: str, selected_index: int) -> bool:
    """Called when the user makes a selection via the API."""
    if choice_id not in _pending_choices:
        return False
    _choice_results[choice_id] = selected_index
    _pending_choices[choice_id].set()
    return True


async def wait_for_choice(choice_id: str, timeout: int = 300, default: int = 0) -> tuple[int, bool]:
    """
    Wait for the user to make a choice.
    Returns (selected_index, was_user_choice).
    If timeout expires, returns (default, False).
    """
    if choice_id not in _pending_choices:
        return default, False

    event = _pending_choices[choice_id]
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        idx = _choice_results.get(choice_id, default)
        return idx, True
    except asyncio.TimeoutError:
        return default, False
    finally:
        # Cleanup
        _pending_choices.pop(choice_id, None)
        _choice_results.pop(choice_id, None)


def has_pending_choice(choice_id: str) -> bool:
    return choice_id in _pending_choices
