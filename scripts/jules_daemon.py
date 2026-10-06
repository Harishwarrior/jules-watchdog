#!/usr/bin/env python3
"""
Jules Autonomous Watchdog Daemon
Monitors Google Jules sessions, auto-approves plans, unblocks stuck agent queries,
detects and resolves stalled IN_PROGRESS/stuck bash sessions, and ensures tasks complete.
Loads API key dynamically from root .env or JULES_API_KEY environment variable.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "https://jules.googleapis.com/v1alpha"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jules_daemon.log")


def load_env_api_key():
    """Load JULES_API_KEY from os.environ or root .env files."""
    if os.environ.get("JULES_API_KEY"):
        return os.environ.get("JULES_API_KEY").strip()

    cur = os.path.abspath(os.getcwd())
    for _ in range(5):
        env_file = os.path.join(cur, ".env")
        if os.path.exists(env_file):
            try:
                with open(env_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("JULES_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip("\"'")
                            if val:
                                return val
            except Exception:
                pass
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


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
    key = load_env_api_key()
    sep = "&" if "?" in endpoint else "?"
    url = f"{BASE_URL}/{endpoint}{sep}key={key}"
    req = urllib.request.Request(url, headers={"X-Goog-Api-Key": key})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def api_post(endpoint, payload=None):
    key = load_env_api_key()
    url = f"{BASE_URL}/{endpoint}?key={key}"
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"X-Goog-Api-Key": key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


# Track sessions prompted to avoid spamming
prompted_sessions = {}


def check_stalled_in_progress(session):
    """
    Detect if an IN_PROGRESS session is stalled (e.g. 'Waiting for the bash session to finish',
    pending user question not surfaced as state transition, or dormant).
    """
    sid = session.get("id") or session.get("name", "").split("/")[-1]
    title = (session.get("title") or "Untitled").split("\n")[0][:60]

    try:
        act_data = api_get(f"sessions/{sid}/activities")
        activities = act_data.get("activities", [])
        if not activities:
            return False

        last_act = activities[-1]
        orig = last_act.get("originator")
        agent_msg = last_act.get("agentMessaged", {}).get("agentMessage", "")

        # Check 1: Agent sent an error or waiting-for-bash message
        is_bash_stuck = "Waiting for the bash session to finish" in agent_msg

        # Check 2: Last message was from agent asking a question, but session remains IN_PROGRESS
        is_unanswered_question = orig == "agent" and (
            agent_msg.strip().endswith("?") or "Do you agree" in agent_msg or "Please clarify" in agent_msg
        )

        now = time.time()
        last_prompt_time = prompted_sessions.get(sid, 0)

        if (is_bash_stuck or is_unanswered_question) and (now - last_prompt_time > 120):
            log(f"⚠️ [STALLED DETECTED] Session {sid} ({title}): bash_stuck={is_bash_stuck}, question={is_unanswered_question}")
            prompt = (
                "Please proceed with the proposed implementation and plan. "
                "Follow standard project conventions, verify using 'fvm flutter analyze' and 'fvm flutter test', "
                "and create the pull request once verified."
            )
            api_post(f"sessions/{sid}:sendMessage", {"prompt": prompt})
            prompted_sessions[sid] = now
            log(f"⚡ [KICK-STARTED STALLED SESSION] Sent unblocking instruction to {sid}")
            return True

    except Exception as e:
        log(f"Error checking activities for {sid}: {e}")

    return False


def process_cycle():
    all_sessions = []
    page_token = None

    while True:
        endpoint = "sessions?pageSize=100"
        if page_token:
            endpoint += f"&pageToken={page_token}"
        try:
            data = api_get(endpoint)
            sessions = data.get("sessions", [])
            all_sessions.extend(sessions)
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        except Exception as e:
            log(f"Error fetching sessions page: {e}")
            break

    pending_plans = []
    stuck_feedback = []
    in_progress = []
    completed = []

    for s in all_sessions:
        sid = s.get("id") or s.get("name").split("/")[-1]
        st = s.get("state")
        src = s.get("sourceContext", {}).get("source", "")
        if "rewardive-mobile" not in src and src:
            continue

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

    # 3. Check and unblock stalled IN_PROGRESS sessions (e.g. bash hang, dormant agent)
    for s in in_progress:
        check_stalled_in_progress(s)

    log(
        f"📊 Status: Active={len(in_progress)} | Approvals={len(pending_plans)} | Feedback={len(stuck_feedback)} | Completed={len(completed)}"
    )

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
    main()
