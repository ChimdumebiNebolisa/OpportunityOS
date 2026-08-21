"""Fail when the checkout contains private artifacts, credentials, or local user paths."""

from __future__ import annotations

import json
from pathlib import Path

from opportunityos.security import audit_public_repository


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = audit_public_repository(root)
    print(
        json.dumps(
            {
                "result": "PASS" if not findings else "FAIL",
                "findings": [finding.__dict__ for finding in findings],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
