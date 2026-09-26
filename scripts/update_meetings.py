#!/usr/bin/env python3
"""EdBeat Watch meeting-source collector.

First milestone: fetch every registered official source, preserve a dated snapshot,
and record whether the source changed. Source-specific meeting parsers plug into
this collector as district coverage expands.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "sources.json"
STATE = ROOT / "data" / "source_state.json"
SNAPSHOTS = ROOT / "archive" / "source-snapshots"
USER_AGENT = "EdBeatWatch/1.0 (Massachusetts school committee public-meeting archive)"


def fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=45) as response:
        return response.read()


def main() -> None:
    registry = json.loads(SOURCES.read_text())
    old = json.loads(STATE.read_text()) if STATE.exists() else {"sources": {}}
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    new_state = {"checked_at": now.isoformat(), "sources": {}}
    changed = []

    for source in registry["sources"]:
        district = source["district"]
        key = district.lower().replace(" ", "-")
        try:
            body = fetch(source["url"])
            digest = hashlib.sha256(body).hexdigest()
            previous = old.get("sources", {}).get(key, {}).get("sha256")
            is_changed = previous is not None and previous != digest
            folder = SNAPSHOTS / key
            folder.mkdir(parents=True, exist_ok=True)
            if previous != digest:
                (folder / f"{stamp}.html").write_bytes(body)
            if is_changed:
                changed.append(district)
            new_state["sources"][key] = {
                "district": district,
                "url": source["url"],
                "sha256": digest,
                "changed": is_changed,
                "last_checked": now.isoformat(),
                "error": None,
            }
        except Exception as exc:
            prior = old.get("sources", {}).get(key, {})
            new_state["sources"][key] = {
                **prior,
                "district": district,
                "url": source["url"],
                "changed": False,
                "last_checked": now.isoformat(),
                "error": str(exc),
            }

    STATE.write_text(json.dumps(new_state, indent=2) + "\n")
    print(f"Checked {len(registry['sources'])} sources; changed: {', '.join(changed) or 'none'}")


if __name__ == "__main__":
    main()
