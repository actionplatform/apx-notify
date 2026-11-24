"""A made-up event of each kind, for `action-platform notify test`."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from action_platform.abc import Event

PAYLOADS = {
    "release.created": {
        "tag": "v1.4.0",
        "version": "1.4.0",
        "name": "Sample release",
        "prerelease": False,
        "changelog": "### Features\n- a sample change",
    },
    "deployment.started": {"stage": "prod", "version": "1.4.0", "executor": "platform"},
    "deployment.succeeded": {
        "target": "app",
        "stage": "prod",
        "version": "1.4.0",
        "executor": "platform",
        "status": "success",
    },
    "deployment.failed": {
        "target": "app",
        "stage": "prod",
        "version": "1.4.0",
        "executor": "platform",
        "status": "failure",
        "error": "sample: the health check did not answer",
    },
    "deployment.verified": {
        "target": "app",
        "stage": "prod",
        "version": "1.4.0",
        "executor": "platform",
        "status": "verified",
    },
    "readiness.blocked": {
        "tag": "v1.4.0",
        "stage": "prod",
        "checks": [
            {"id": "sample.check", "detail": "a sample failure", "fix": "nothing to do"}
        ],
    },
    "ci.failed": {"tag": "v1.4.0", "run": 42, "name": "publish", "status": "failure"},
}


def sample(kind: str) -> Event:
    if kind not in PAYLOADS:
        raise ValueError(f"{kind}: one of {', '.join(PAYLOADS)}")

    return Event(
        kind,
        "sample-org",
        "sample-project",
        "sample-app",
        actor="apx-notify test",
        payload=PAYLOADS[kind],
        id=str(uuid.uuid4()),
        at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
