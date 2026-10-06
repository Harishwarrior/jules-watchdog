#!/usr/bin/env python3
"""
Jules Autonomous Watchdog Daemon
Monitors Google Jules sessions, auto-approves plans, unblocks stuck agent queries,
detects and resolves stalled IN_PROGRESS/stuck bash sessions, revives pseudo-completed sessions
without PRs that have unapproved plans or pending questions, and ensures all tasks produce PRs.
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
approved_plans = set()


def check_and_handle_session_activity(session):
    """
    Examines a session's activity timeline.
    Handles:
    1. Unapproved generated plans (approves them and kicks execution).
    2. Stalled IN_PROGRESS sessions (bash hanging, dormant agent).
    3. Pseudo-completed sessions that have NO PR outputs but have pending plans or questions.
    """
    sid = session.get("id") or session.get("name", "").split("/")[-1]
    title = (session.get("title") or "Untitled").split("\n")[0][:60]
    st = session.get("state")

    # If already has a pull request output, it is truly complete
    outputs = session.get("outputs", [])
    if any(o.get("pullRequest") for o in outputs):
        return False

    try:
        act_data = api_get(f"sessions/{sid}/activities")
        activities = act_data.get("activities", [])
        if not activities:
            return False

        # Check for unapproved plans
        has_plan = False
        has_approval = False
        for a in activities:
            if "planGenerated" in a:
                has_plan = True
            if "planApproved" in a:
                has_approval = True

        if has_plan and not has_approval and sid not in approved_plans:
            log(f"⚡ [AUTO-APPROVE DETECTED PLAN] Session {sid} ({title})")
            try:
                api_post(f"sessions/{sid}:approvePlan")
                approved_plans.add(sid)
                kick_prompt = (
                    "Plan approved. Please execute the plan now, verify with fvm flutter analyze "
                    "and fvm flutter test, and create the pull request."
                )
                api_post(f"sessions/{sid}:sendMessage", {"prompt": kick_prompt})
                log(f"✅ Approved plan and kicked session {sid}")
                return True
            except Exception as e:
                log(f"❌ Failed approving plan for {sid}: {e}")

        # Check latest activity
        last_act = activities[-1]
        orig = last_act.get("originator")
        agent_msg = last_act.get("agentMessaged", {}).get("agentMessage", "")

        is_bash_stuck = "Waiting for the bash session to finish" in agent_msg
        is_unanswered_question = orig == "agent" and (
            agent_msg.strip().endswith("?") or "clarify" in agent_msg or "Do you agree" in agent_msg
        )

        now = time.time()
        last_prompt_time = prompted_sessions.get(sid, 0)

        # Trigger if hung on bash, question unanswered, or pseudo-completed without PR
        needs_kick = is_bash_stuck or is_unanswered_question or (st == "COMPLETED" and not outputs)

        if needs_kick and (now - last_prompt_time > 120):
            log(f"⚠️ [REVIVING/UNBLOCKING] Session {sid} ({title}): state={st}, bash={is_bash_stuck}, question={is_unanswered_question}")
            prompt = (
                "Please proceed with the proposed implementation. "
                "Follow standard project conventions, verify using 'fvm flutter analyze' and 'fvm flutter test', "
                "and create the pull request once verified."
            )
            api_post(f"sessions/{sid}:sendMessage", {"prompt": prompt})
            prompted_sessions[sid] = now
            log(f"⚡ [PROMPT SENT] Revived session {sid}")
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
    completed_with_pr = []
    incomplete_completed = []

    for s in all_sessions:
        sid = s.get("id") or s.get("name").split("/")[-1]
        st = s.get("state")
        src = s.get("sourceContext", {}).get("source", "")
        if "rewardive-mobile" not in src and src:
            continue

        outputs = s.get("outputs", [])
        has_pr = any(o.get("pullRequest") for o in outputs)

        if st == "AWAITING_PLAN_APPROVAL":
            pending_plans.append(s)
        elif st == "AWAITING_USER_FEEDBACK":
            stuck_feedback.append(s)
        elif st == "IN_PROGRESS":
            in_progress.append(s)
        elif st == "COMPLETED":
            if has_pr:
                completed_with_pr.append(s)
            else:
                incomplete_completed.append(s)

    # 1. Auto-approve all explicit plans
    for s in pending_plans:
        sid = s.get("id") or s.get("name").split("/")[-1]
        title = (s.get("title") or "Untitled").split("\n")[0][:60]
        try:
            api_post(f"sessions/{sid}:approvePlan")
            log(f"⚡ [PLAN APPROVED] Session {sid} ({title})")
        except Exception as e:
            log(f"❌ [APPROVE FAILED] Session {sid}: {e}")

    # 2. Unblock all sessions explicitly awaiting feedback
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

    # 3. Handle stalled IN_PROGRESS sessions
    for s in in_progress:
        check_and_handle_session_activity(s)

    # 4. Handle pseudo-completed sessions without PRs
    for s in incomplete_completed:
        check_and_handle_session_activity(s)

    log(
        f"📊 Status: Active={len(in_progress)} | Approvals={len(pending_plans)} | Feedback={len(stuck_feedback)} | Completed(PR)={len(completed_with_pr)} | NeedsPR={len(incomplete_completed)}"
    )

    return len(pending_plans) > 0 or len(stuck_feedback) > 0 or len(in_progress) > 0 or len(incomplete_completed) > 0


def main(interval=20):
    log("🚀 Jules Daemon started.")
    while True:
        try:
            has_active = process_cycle()
            if not has_active:
                log("🎉 All sessions reached terminal state and created PRs!")
                break
        except Exception as e:
            log(f"⚠️ Error during cycle: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
