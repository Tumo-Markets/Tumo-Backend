import json
import os
from typing import Any, Dict, Optional

import requests

# ================== CONFIG ==================
RPC_URL = os.getenv("RPC_URL", "https://rpc-testnet.onelabs.cc:443")

PACKAGE_ID = "0x31b6ea6f6c2e1727d590fba2b6ccd93dd0785f238fd91cb16030d468a466bc6e"
MODULE = "tumo_markets_core"

EVENT_TYPES = [
    f"{PACKAGE_ID}::{MODULE}::PositionOpened",
    f"{PACKAGE_ID}::{MODULE}::PositionUpdated",
    f"{PACKAGE_ID}::{MODULE}::PositionClosed",
    f"{PACKAGE_ID}::{MODULE}::PositionLiquidated",  # ✅ ADD THIS
]

LIMIT_PER_PAGE = 50
MAX_PAGES = 3  # tăng nếu muốn quét sâu
# ============================================


def rpc_call(method: str, params: list) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    r = requests.post(RPC_URL, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]


def query_events(
    move_event_type: str,
    cursor: Optional[Dict[str, Any]] = None,
    limit: int = 50,
    descending: bool = True,
) -> Dict[str, Any]:
    query = {"MoveEventType": move_event_type}
    return rpc_call(
        "suix_queryEvents",
        [query, cursor, limit, descending],
    )


def print_raw_event(event: Dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False, indent=2))
    print("-" * 100)


def fetch_and_print_events(event_type: str) -> None:
    print("=" * 100)
    print(f"EVENT TYPE: {event_type}")
    print("=" * 100)

    cursor = None
    page = 0

    while page < MAX_PAGES:
        res = query_events(
            move_event_type=event_type,
            cursor=cursor,
            limit=LIMIT_PER_PAGE,
            descending=True,
        )

        events = res.get("data") or res.get("events") or []
        next_cursor = res.get("nextCursor") or res.get("next_cursor")
        has_next = res.get("hasNextPage") or res.get("has_next_page")

        if not events:
            print("No events found.")
            break

        for e in events:
            print_raw_event(e)

        if not has_next:
            break

        cursor = next_cursor
        page += 1


def main():
    print(f"RPC_URL: {RPC_URL}")
    print(f"PACKAGE_ID: {PACKAGE_ID}")
    print()

    for event_type in EVENT_TYPES:
        fetch_and_print_events(event_type)


if __name__ == "__main__":
    main()
