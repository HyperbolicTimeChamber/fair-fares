#!/usr/bin/env python3
"""Block until the form sends an event, then print it as JSON.

  python3 wait_event.py --types start,book [--after ID] [--timeout 540]

Without --after, only events newer than the moment this script started count.
Exit code 0 = event printed; 2 = timeout (just run it again; agents' shell calls have time limits).
"""
import json, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import STATE

EVENTS = STATE / "events.jsonl"


def read():
    if not EVENTS.exists():
        return []
    with open(EVENTS, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    a = sys.argv[1:]
    types = set((a[a.index("--types") + 1] if "--types" in a else "start,book").split(","))
    timeout = float(a[a.index("--timeout") + 1]) if "--timeout" in a else 540
    after = int(a[a.index("--after") + 1]) if "--after" in a else (read()[-1]["id"] if read() else 0)
    end = time.time() + timeout
    while time.time() < end:
        for ev in read():
            if ev["id"] > after and ev["type"] in types:
                print(json.dumps(ev, ensure_ascii=False))
                return 0
        time.sleep(1)
    print(json.dumps({"timeout": True, "after": after}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
