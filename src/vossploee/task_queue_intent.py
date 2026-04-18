"""Heuristics for when a new queue01 root should use LIFO claim order (see TaskQueuePolicy)."""

from __future__ import annotations

import re


def decomposer_root_should_use_lifo(title: str, description: str) -> bool:
    """True when the user is clearly asking to remove/cancel/clear queued work or override routine runs.

    Used to force ``queue_policy=lifo`` so the new root is claimed before older fifo monitoring roots.
    """
    t = f"{title}\n{description}".lower()
    if not re.search(
        r"\b(remove|delete|deleted|cancel|clear|cleared|purge|drop|stop|abort)\b",
        t,
    ):
        return False
    return bool(
        re.search(
            r"\b(task|tasks|queue|queued|scheduler|scheduled|schedule|monitor|monitoring|run|root|all)\b",
            t,
        )
        or ("all" in t and "upwork" in t)
    )
