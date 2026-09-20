#!/usr/bin/env python3
"""
Jules Watchdog Monitor & Automation Daemon

Monitors Google Jules coding sessions / tasks for rewardive-mobile (or specified repository),
automatically handling plan approvals, feedback requests, and state reporting.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_REPO = "github/rewardive/rewardive-mobile"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "../../.."))
STATE_FILE = os.path.join(SCRIPT_DIR, "watchdog_state.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "watchdog.log")


def log(msg, to_file=True):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    if to_file:
        try:
            with open(LOG_FILE, "a") as f:
                f.write(formatted + "\n")
        except Exception:
            pass


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "known_tasks": {},
        "approved_plans": {},
        "completed_tasks": {},
        "failed_tasks": {},
        "events": [],
    }


def save_state(state):
    try:
        if len(state.get("events", [])) > 300:
            state["events"] = state["events"][-300:]
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"Error saving state: {e}")


def record_event(state, event_type, task_id, details=""):
    event = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "type": event_type,
        "task_id": task_id,
        "details": details,
    }
    state.setdefault("events", []).append(event)
    save_state(state)


def refresh_token_if_needed():
    """Trigger token refresh via jules CLI if OAuth expired."""
    try:
        subprocess.run(
            ["/home/linuxbrew/.linuxbrew/bin/jules", "remote", "list", "--session"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as e:
        log(f"Token refresh error: {e}")


def get_token():
    """Retrieve OAuth token from system keyring or secretstorage."""
    try:
        import keyring

        token_data = json.loads(keyring.get_password("jules-cli", "default"))
        return token_data.get("access_token")
    except Exception:
        pass

    try:
        import secretstorage

        bus = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(bus)
        for item in collection.get_all_items():
            if item.get_attributes().get("service") == "jules-cli":
                secret = item.get_secret().decode("utf-8")
                return json.loads(secret).get("access_token")
    except Exception:
        pass

    return None


def api_call(url, method="GET", payload=None):
    token = get_token()
    if not token:
        refresh_token_if_needed()
        token = get_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            log("Token expired (401). Refreshing token...")
            refresh_token_if_needed()
            token = get_token()
            headers["Authorization"] = f"Bearer {token}"
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode())
        raise


def is_task_active(t):
    ts = t.get("taskStatus")
    sts = t.get("swebotTaskStatus")
    if ts in ["COMPLETED", "FAILED"] or sts in [
        "SWEBOT_TASK_STATUS_COMPLETED",
        "SWEBOT_TASK_STATUS_FAILED",
    ]:
        return False
    return True


def get_tasks_for_repo(repo_name=DEFAULT_REPO):
    status, data = api_call("https://aida.googleapis.com/v1/swebot/tasks?pageSize=100")
    tasks = data.get("tasks", [])
    repo_tasks = [t for t in tasks if t.get("sourceId") == repo_name]
    active = [t for t in repo_tasks if is_task_active(t)]
    return active, repo_tasks


def approve_plan(task_id):
    url = f"https://aida.googleapis.com/v1/swebot/tasks/{task_id}:interact"
    payload = {"taskId": task_id, "userActivity": {"planApproved": {}}}
    try:
        api_call(url, method="POST", payload=payload)
        return True, None
    except Exception as e:
        try:
            fb_payload = {
                "taskId": task_id,
                "userActivity": {
                    "feedbackGiven": {
                        "feedback": "Plan approved. Please proceed with implementation."
                    }
                },
            }
            api_call(url, method="POST", payload=fb_payload)
            return True, None
        except Exception as e2:
            return False, f"{e}; fallback: {e2}"


def provide_feedback(
    task_id,
    answer="Please proceed with the proposed implementation following project conventions.",
):
    url = f"https://aida.googleapis.com/v1/swebot/tasks/{task_id}:interact"
    payload = {
        "taskId": task_id,
        "userActivity": {"feedbackGiven": {"feedback": answer}},
    }
    try:
        api_call(url, method="POST", payload=payload)
        return True, None
    except Exception as e:
        return False, str(e)


def handle_task(task_id, state):
    url = f"https://aida.googleapis.com/v1/swebot/tasks/{task_id}"
    _, data = api_call(url)
    task = data.get("task", {})
    swebot_status = task.get("swebotTaskStatus")
    task_status = task.get("taskStatus")
    title = task.get("suggestedTitle") or task.get("title") or "Untitled Task"
    latest_plan = task.get("latestPlan", {})
    plan_id = latest_plan.get("id")
    steps = latest_plan.get("steps", [])
    is_awaiting_review = task.get("isAwaitingReview", False)
    in_prog = task.get("inProgressWork", {})
    step_title = in_prog.get("planStep", {}).get("title", "") if in_prog else ""
    step_idx = in_prog.get("planStep", {}).get("index", "") if in_prog else ""

    info = {
        "id": task_id,
        "title": title,
        "taskStatus": task_status,
        "swebotStatus": swebot_status,
        "step_idx": step_idx,
        "step_title": step_title,
        "plan_id": plan_id,
    }

    # Check for plan approval condition
    needs_plan_approval = (
        task_status == "AWAITING_PLAN_APPROVAL"
        or swebot_status == "SWEBOT_TASK_STATUS_AWAITING_PLAN_APPROVAL"
        or is_awaiting_review
        or (
            plan_id
            and steps
            and state.get("approved_plans", {}).get(task_id) != plan_id
            and task_status not in ["COMPLETED", "FAILED"]
        )
    )

    if needs_plan_approval:
        log(f"⚡ [AUTO-APPROVE] Approving plan for task {task_id} ('{title}')...")
        ok, err = approve_plan(task_id)
        if ok:
            log(f"✅ Successfully approved plan for task {task_id}")
            state.setdefault("approved_plans", {})[task_id] = plan_id or "approved"
            record_event(state, "PLAN_APPROVED", task_id, f"Plan approved for: {title}")
        else:
            log(f"❌ Failed to approve plan for task {task_id}: {err}")
            record_event(state, "PLAN_APPROVE_ERROR", task_id, str(err))

    # Check for feedback condition
    needs_feedback = (
        task_status == "AWAITING_USER_FEEDBACK"
        or swebot_status == "SWEBOT_TASK_STATUS_AWAITING_USER_FEEDBACK"
    )

    if needs_feedback:
        log(f"💬 [AUTO-FEEDBACK] Providing feedback for task {task_id} ('{title}')...")
        act_steps = task.get("activitySteps", [])
        last_question = ""
        for s in reversed(act_steps):
            q = s.get("agentActivity", {}).get("userQuestion", {}).get("question")
            if q:
                last_question = q
                break
        answer = "Please proceed with the proposed implementation following project conventions."
        if last_question:
            log(f"Responding to question: {last_question[:80]}...")
        ok, err = provide_feedback(task_id, answer)
        if ok:
            log(f"✅ Successfully provided feedback for task {task_id}")
            record_event(
                state, "FEEDBACK_GIVEN", task_id, f"Feedback sent for: {title}"
            )
        else:
            log(f"❌ Failed to provide feedback for task {task_id}: {err}")
            record_event(state, "FEEDBACK_ERROR", task_id, str(err))

    return info


def check_status(repo_name=DEFAULT_REPO):
    """One-shot status check and display."""
    active_tasks, all_tasks = get_tasks_for_repo(repo_name)
    state = load_state()

    print(f"\n=======================================================")
    print(f" Jules Watchdog Status Report: {repo_name}")
    print(f"=======================================================")
    print(f"Total Tasks Tracked: {len(all_tasks)}")
    print(f"Currently Active:    {len(active_tasks)}")

    completed = [
        t
        for t in all_tasks
        if t.get("swebotTaskStatus") == "SWEBOT_TASK_STATUS_COMPLETED"
        or t.get("taskStatus") == "COMPLETED"
    ]
    failed = [
        t
        for t in all_tasks
        if t.get("swebotTaskStatus") == "SWEBOT_TASK_STATUS_FAILED"
        or t.get("taskStatus") == "FAILED"
    ]

    print(f"Completed:           {len(completed)}")
    print(f"Failed / Stale:      {len(failed)}")

    if active_tasks:
        print(f"\nActive Tasks ({len(active_tasks)}):")
        for t in active_tasks:
            tid = t.get("id")
            title = t.get("suggestedTitle") or t.get("title") or "Untitled Task"
            st = t.get("swebotTaskStatus") or t.get("taskStatus")
            print(f"  • [{st}] {tid}: {title}")
    else:
        print("\nNo tasks currently awaiting approval or active.")

    recent_events = state.get("events", [])[-5:]
    if recent_events:
        print(f"\nRecent Events (Last 5):")
        for ev in recent_events:
            print(f"  [{ev.get('time')}] {ev.get('type')}: {ev.get('details')}")
    print(f"=======================================================\n")


def run_watchdog_loop(poll_interval=20, repo_name=DEFAULT_REPO, oneshot=False):
    if oneshot:
        check_status(repo_name)
        return

    log(f"Starting Jules Watchdog Daemon for {repo_name} (poll interval: {poll_interval}s)...")
    state = load_state()

    while True:
        try:
            active_tasks, all_tasks = get_tasks_for_repo(repo_name)

            for t in all_tasks:
                tid = t.get("id")
                if tid not in state["known_tasks"]:
                    title = t.get("suggestedTitle") or t.get("title") or "Untitled Task"
                    log(f"🆕 [NEW TASK DETECTED] Task {tid}: '{title}'")
                    record_event(state, "NEW_TASK", tid, title)
                    state["known_tasks"][tid] = {
                        "title": title,
                        "status": t.get("taskStatus"),
                        "swebotStatus": t.get("swebotTaskStatus"),
                        "first_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }

            active_ids = set()
            for t in active_tasks:
                tid = t.get("id")
                active_ids.add(tid)
                info = handle_task(tid, state)
                prev_status = state["known_tasks"].get(tid, {}).get("status")
                cur_status = info.get("taskStatus") or info.get("swebotStatus")
                if prev_status != cur_status:
                    log(
                        f"🔄 [STATUS CHANGE] Task {tid} ('{info.get('title')}'): {prev_status} -> {cur_status}"
                    )
                    record_event(
                        state, "STATUS_CHANGE", tid, f"{prev_status} -> {cur_status}"
                    )
                    state["known_tasks"].setdefault(tid, {})["status"] = cur_status
                    state["known_tasks"][tid]["swebotStatus"] = info.get("swebotStatus")

            for tid, tinfo in list(state["known_tasks"].items()):
                if tinfo.get("status") not in [
                    "COMPLETED",
                    "FAILED",
                    "SWEBOT_TASK_STATUS_COMPLETED",
                    "SWEBOT_TASK_STATUS_FAILED",
                ]:
                    if tid not in active_ids:
                        try:
                            _, d = api_call(
                                f"https://aida.googleapis.com/v1/swebot/tasks/{tid}"
                            )
                            curr_task = d.get("task", {})
                            final_status = curr_task.get("taskStatus") or curr_task.get(
                                "swebotTaskStatus"
                            )
                            log(
                                f"🏁 [TASK COMPLETED/ENDED] Task {tid} ('{tinfo.get('title')}') finalized with status: {final_status}"
                            )
                            record_event(
                                state,
                                "TASK_FINISHED",
                                tid,
                                f"Final status: {final_status}",
                            )
                            tinfo["status"] = final_status
                        except Exception:
                            pass

            save_state(state)

        except Exception as e:
            log(f"⚠️ Watchdog iteration error: {e}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jules Watchdog Monitoring Daemon")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Repository source ID (e.g. github/owner/repo)")
    parser.add_argument("--interval", type=int, default=20, help="Polling interval in seconds")
    parser.add_argument("--status", action="store_true", help="Print current status and exit")
    args = parser.parse_args()

    run_watchdog_loop(poll_interval=args.interval, repo_name=args.repo, oneshot=args.status)
