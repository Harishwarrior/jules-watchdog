#!/usr/bin/env python3
"""
Jules Autonomous Watchdog Daemon
Monitors Google Jules sessions, auto-approves plans, answers agent queries,
and ensures tasks run through to completion.
Supports Google Jules v1alpha API via JULES_API_KEY env var or --api-key.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_KEY = os.environ.get("JULES_API_KEY", "")
BASE_URL = "https://jules.googleapis.com/v1alpha"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jules_daemon.log")


def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{t}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def api_get(endpoint):
    sep = "&" if "?" in endpoint else "?"
    url = f"{BASE_URL}/{endpoint}"
    headers = {}
    if API_KEY:
        url = f"{url}{sep}key={API_KEY}"
        headers["X-Goog-Api-Key"] = API_KEY
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def api_post(endpoint, payload=None):
    sep = "&" if "?" in endpoint else "?"
    url = f"{BASE_URL}/{endpoint}"
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        url = f"{url}{sep}key={API_KEY}"
        headers["X-Goog-Api-Key"] = API_KEY
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def process_cycle():
    data = api_get("sessions")
    sessions = data.get("sessions", [])

    counts = {}
    pending_plans = []
    stuck_feedback = []
    in_progress = []
    completed = []

    for s in sessions:
        sid = s.get("id") or s.get("name").split("/")[-1]
        st = s.get("state")
        counts[st] = counts.get(st, 0) + 1

        if st == "AWAITING_PLAN_APPROVAL":
            pending_plans.append(s)
        elif st == "AWAITING_USER_FEEDBACK":
            stuck_feedback.append(s)
        elif st == "IN_PROGRESS":
            in_progress.append(s)
        elif st == "COMPLETED":
            completed.append(s)

    # 1. Auto-approve all plans
    for s in pending_plans:
        sid = s.get("id") or s.get("name").split("/")[-1]
        title = (s.get("title") or "Untitled").split("\n")[0][:60]
        try:
            api_post(f"sessions/{sid}:approvePlan")
            log(f"⚡ [PLAN APPROVED] Session {sid} ({title})")
        except Exception as e:
            log(f"❌ [APPROVE FAILED] Session {sid}: {e}")

    # 2. Unblock all sessions awaiting feedback
    for s in stuck_feedback:
        sid = s.get("id") or s.get("name").split("/")[-1]
        title = (s.get("title") or "Untitled").split("\n")[0][:60]
        try:
            prompt_text = (
                "Please proceed with the proposed implementation. "
                "Follow standard project conventions, verify using 'fvm flutter analyze' and 'fvm flutter test', "
                "and create the pull request once verified."
            )
            api_post(f"sessions/{sid}:sendMessage", {"prompt": prompt_text})
            log(f"💬 [PROMPT SENT] Session {sid} ({title})")
        except Exception as e:
            log(f"❌ [PROMPT FAILED] Session {sid}: {e}")

    log(
        f"📊 Status: Active={len(in_progress)} | Approvals={len(pending_plans)} | Feedback={len(stuck_feedback)} | Completed={len(completed)}"
    )

    # Return True if any active tasks remain
    return len(pending_plans) > 0 or len(stuck_feedback) > 0 or len(in_progress) > 0


def main(interval=20):
    log("🚀 Jules Daemon started.")
    while True:
        try:
            has_active = process_cycle()
            if not has_active:
                log("🎉 All sessions reached terminal state (Completed/Failed)!")
                break
        except Exception as e:
            log(f"⚠️ Error during cycle: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jules Autonomous Watchdog Daemon")
    parser.add_argument("--api-key", default=os.environ.get("JULES_API_KEY", ""), help="Google Jules API key (or set JULES_API_KEY env var)")
    parser.add_argument("--interval", type=int, default=20, help="Cycle interval in seconds (default: 20)")
    args = parser.parse_args()

    if args.api_key:
        API_KEY = args.api_key

    main(interval=args.interval)
