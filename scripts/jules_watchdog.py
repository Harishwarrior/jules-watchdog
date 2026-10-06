#!/usr/bin/env python3
"""
Jules Watchdog Monitor & Automation Daemon

Monitors Google Jules coding sessions / tasks for any repository (auto-detected or specified),
automatically handling plan approvals, feedback requests, pagination, and state reporting.
Supports both Google Jules v1alpha API (API Key from root .env or JULES_API_KEY env var) and OAuth.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_REPO = "github/rewardive/rewardive-server"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "watchdog_state.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "watchdog.log")

JULES_BASE_URL = "https://jules.googleapis.com/v1alpha"


def detect_repo_source_id():
    """Detect repo sourceId from git remote origin or fall back to DEFAULT_REPO."""
    try:
        url = (
            subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            .strip()
        )
        if "github.com" in url:
            part = url.split("github.com", 1)[1].lstrip(":").lstrip("/")
            if part.endswith(".git"):
                part = part[:-4]
            return f"github/{part}"
    except Exception:
        pass
    return DEFAULT_REPO


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


JULES_API_KEY = load_env_api_key() or ""


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
        if len(state.get("events", [])) > 500:
            state["events"] = state["events"][-500:]
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


def find_jules_binary():
    """Locate jules binary across common locations."""
    for loc in [
        shutil.which("jules"),
        "/opt/homebrew/bin/jules",
        "/usr/local/bin/jules",
        "/home/linuxbrew/.linuxbrew/bin/jules",
        os.path.expanduser("~/.local/bin/jules"),
    ]:
        if loc and os.path.isfile(loc) and os.access(loc, os.X_OK):
            return loc
    return "jules"


def refresh_token_if_needed():
    """Trigger token refresh via jules CLI if OAuth expired."""
    jules_bin = find_jules_binary()
    try:
        subprocess.run(
            [jules_bin, "remote", "list", "--session"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as e:
        log(f"Token refresh error: {e}")


def get_token():
    """Retrieve OAuth token from macOS keychain, system keyring, or secretstorage."""
    # 1. macOS Keychain (standard for macOS installations)
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["security", "find-generic-password", "-s", "jules-cli", "-w"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            if out.startswith("go-keyring-base64:"):
                raw = base64.b64decode(out.split(":", 1)[1])
                return json.loads(raw).get("access_token")
            elif out:
                return json.loads(out).get("access_token")
        except Exception:
            pass

    # 2. Python keyring library
    try:
        import keyring

        token_data = json.loads(keyring.get_password("jules-cli", "default"))
        return token_data.get("access_token")
    except Exception:
        pass

    # 3. Linux SecretStorage
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


def jules_api_request(endpoint, method="GET", payload=None):
    """Call Google Jules v1alpha API using API Key or OAuth Bearer token."""
    global JULES_API_KEY
    if not JULES_API_KEY:
        JULES_API_KEY = load_env_api_key() or ""

    url = f"{JULES_BASE_URL}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
    }

    if JULES_API_KEY:
        sep = "&" if "?" in endpoint else "?"
        url = f"{url}{sep}key={JULES_API_KEY}"
        headers["X-Goog-Api-Key"] = JULES_API_KEY
    else:
        token = get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            raise ValueError(
                "No Jules credentials found. Set JULES_API_KEY in root .env or environment variable, "
                "pass --api-key, or authenticate with 'jules login'."
            )

    data = json.dumps(payload).encode("utf-8") if payload is not None else None

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401 and not JULES_API_KEY:
            log("Received 401 Unauthorized with OAuth token, attempting refresh...")
            refresh_token_if_needed()
            token = get_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req) as resp:
                    return resp.status, json.loads(resp.read().decode())
        raise


def get_all_sessions_for_repo(repo_name=DEFAULT_REPO):
    """Retrieve ALL sessions with full pagination."""
    repo_normalized = repo_name.replace("github/", "").replace("sources/", "")
    all_sessions = []
    page_token = None

    while True:
        endpoint = "sessions?pageSize=100"
        if page_token:
            endpoint += f"&pageToken={page_token}"
        try:
            _, data = jules_api_request(endpoint)
            sessions = data.get("sessions", [])
            all_sessions.extend(sessions)
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        except Exception as e:
            log(f"Error fetching sessions page: {e}")
            break

    # Filter to matching repo source
    repo_sessions = []
    for s in all_sessions:
        src = s.get("sourceContext", {}).get("source", "")
        if not repo_normalized or repo_normalized in src or not src:
            repo_sessions.append(s)

    active = [s for s in repo_sessions if s.get("state") not in ["COMPLETED", "FAILED"]]
    return active, repo_sessions


def approve_session_plan(session_id):
    """Approve execution plan for a session."""
    endpoint = f"sessions/{session_id}:approvePlan"
    try:
        jules_api_request(endpoint, method="POST", payload={})
        return True, None
    except Exception as e:
        return False, str(e)


def send_session_message(session_id, prompt):
    """Send user instruction/answer to unblock session."""
    endpoint = f"sessions/{session_id}:sendMessage"
    payload = {"prompt": prompt}
    try:
        jules_api_request(endpoint, method="POST", payload=payload)
        return True, None
    except Exception as e:
        return False, str(e)


def get_unblock_instruction(repo_name="", title=""):
    """Generate stack-aware unblocking response for Jules."""
    repo_lower = repo_name.lower()
    if os.path.exists("go.mod") or "rewardive-server" in repo_lower or "go" in repo_lower:
        return (
            "Please proceed with the proposed implementation following Go conventions and standard project patterns. "
            "Verify with 'go test ./...' and 'go vet ./...', and create the pull request once verified."
        )
    elif os.path.exists("pubspec.yaml") or "rewardive-mobile" in repo_lower or "flutter" in repo_lower:
        return (
            "Please proceed with the proposed implementation following Flutter conventions. "
            "Verify using 'flutter analyze' and 'flutter test', and create the pull request once verified."
        )
    elif os.path.exists("package.json"):
        return (
            "Please proceed with the proposed implementation following project conventions. "
            "Verify using 'npm test', and create the pull request once verified."
        )
    elif os.path.exists("pyproject.toml") or os.path.exists("requirements.txt"):
        return (
            "Please proceed with the proposed implementation following Python conventions. "
            "Verify using pytest, and create the pull request once verified."
        )
    return (
        "Please proceed with the proposed implementation following project conventions. "
        "Verify your changes with tests, and create the pull request once verified."
    )


def archive_session(session_id):
    """Archive a session via Google Jules v1alpha API."""
    try:
        jules_api_request(f"sessions/{session_id}:archive", method="POST", payload={})
        return True, None
    except Exception as e:
        return False, e


def archive_completed_sessions(repo_name=DEFAULT_REPO, api_key=None):
    """Find and archive all completed tasks that have created pull requests."""
    global JULES_API_KEY
    if api_key:
        JULES_API_KEY = api_key

    log(f"📦 Checking sessions to archive for {repo_name}...")
    _, all_sessions = get_all_sessions_for_repo(repo_name)
    to_archive = []
    for s in all_sessions:
        sid = s.get("id") or s.get("name", "").split("/")[-1]
        outputs = s.get("outputs", [])
        if any(o.get("pullRequest") for o in outputs):
            title = (s.get("title") or "Untitled Task").split("\n")[0].strip()
            to_archive.append((sid, title))

    log(f"Found {len(to_archive)} completed sessions with PRs to archive.")
    count = 0
    for sid, title in to_archive:
        ok, err = archive_session(sid)
        if ok:
            count += 1
            if count % 10 == 0:
                log(f"Archived {count}/{len(to_archive)} sessions...")
        else:
            log(f"Failed archiving {sid}: {err}")

    log(f"🎉 Successfully archived {count}/{len(to_archive)} sessions.")
    return count


def handle_session(session, state):
    sid = session.get("id") or session.get("name", "").split("/")[-1]
    st = session.get("state")
    title = (session.get("title") or "Untitled Task").split("\n")[0].strip()
    src_repo = session.get("sourceContext", {}).get("source", "")

    info = {
        "id": sid,
        "title": title,
        "state": st,
    }

    # 1. Auto-approve plan
    if st == "AWAITING_PLAN_APPROVAL":
        log(f"⚡ [AUTO-APPROVE] Approving plan for session {sid} ('{title}')...")
        ok, err = approve_session_plan(sid)
        if ok:
            log(f"✅ Successfully approved plan for session {sid}")
            record_event(state, "PLAN_APPROVED", sid, f"Plan approved for: {title}")
            info["state"] = "IN_PROGRESS"
        else:
            log(f"❌ Failed to approve plan for session {sid}: {err}")
            record_event(state, "PLAN_APPROVE_ERROR", sid, str(err))

    # 2. Auto-unblock feedback
    elif st == "AWAITING_USER_FEEDBACK":
        log(f"💬 [AUTO-FEEDBACK] Sending unblocking prompt for session {sid} ('{title}')...")
        answer = get_unblock_instruction(repo_name=src_repo, title=title)
        ok, err = send_session_message(sid, answer)
        if ok:
            log(f"✅ Successfully sent unblocking prompt for session {sid}")
            record_event(state, "FEEDBACK_GIVEN", sid, f"Feedback sent for: {title}")
            info["state"] = "FEEDBACK_SENT"
        else:
            log(f"❌ Failed to send prompt for session {sid}: {err}")
            record_event(state, "FEEDBACK_ERROR", sid, str(err))

    # 3. Auto-archive completed sessions with PRs
    elif st == "COMPLETED":
        outputs = session.get("outputs", [])
        if any(o.get("pullRequest") for o in outputs):
            archive_session(sid)

    return info


def check_status(repo_name=DEFAULT_REPO, api_key=None):
    global JULES_API_KEY
    if api_key:
        JULES_API_KEY = api_key

    active_sessions, all_sessions = get_all_sessions_for_repo(repo_name)
    state = load_state()

    print(f"\n=======================================================")
    print(f" Jules Watchdog Status Report: {repo_name}")
    print(f"=======================================================")
    print(f"Total Sessions Tracked: {len(all_sessions)}")
    print(f"Currently Active:       {len(active_sessions)}")

    completed = [s for s in all_sessions if s.get("state") == "COMPLETED"]
    failed = [s for s in all_sessions if s.get("state") == "FAILED"]

    print(f"Completed:              {len(completed)}")
    print(f"Failed / Stale:         {len(failed)}")

    if active_sessions:
        print(f"\nActive Sessions ({len(active_sessions)}):")
        for s in active_sessions:
            sid = s.get("id") or s.get("name", "").split("/")[-1]
            title = (s.get("title") or "Untitled Task").split("\n")[0].strip()
            st = s.get("state")
            print(f"  • [{st}] {sid}: {title}")
    else:
        print("\nNo sessions currently active or awaiting approval.")

    recent_events = state.get("events", [])[-5:]
    if recent_events:
        print(f"\nRecent Events (Last 5):")
        for ev in recent_events:
            print(f"  [{ev.get('time')}] {ev.get('type')}: {ev.get('details')}")
    print(f"=======================================================\n")


def trigger_all_active(repo_name=DEFAULT_REPO, api_key=None):
    """One-shot sweep: unblock all sessions currently awaiting user feedback or plan approval."""
    global JULES_API_KEY
    if api_key:
        JULES_API_KEY = api_key

    log(f"🚀 Triggering all active agent tasks for {repo_name}...")
    active_sessions, all_sessions = get_all_sessions_for_repo(repo_name)
    state = load_state()

    actionable = [
        s for s in active_sessions
        if s.get("state") in ["AWAITING_PLAN_APPROVAL", "AWAITING_USER_FEEDBACK"]
    ]

    log(f"Found {len(active_sessions)} active sessions ({len(actionable)} actionable).")

    processed = 0
    for s in actionable:
        sid = s.get("id") or s.get("name", "").split("/")[-1]
        title = (s.get("title") or "Untitled Task").split("\n")[0].strip()
        st = s.get("state")
        log(f"[{processed+1}/{len(actionable)}] Handling {sid} [{st}]: {title[:50]}...")
        handle_session(s, state)
        processed += 1
        time.sleep(0.5)

    save_state(state)
    log(f"✨ Sweep complete! Successfully processed {processed} actionable sessions.")


def run_watchdog_loop(poll_interval=20, repo_name=DEFAULT_REPO, oneshot=False, trigger_all=False, api_key=None):
    global JULES_API_KEY
    if api_key:
        JULES_API_KEY = api_key

    if trigger_all:
        trigger_all_active(repo_name=repo_name, api_key=api_key)
        return

    if oneshot:
        check_status(repo_name, api_key=api_key)
        return

    log(f"Starting Jules Watchdog Daemon for {repo_name} (poll interval: {poll_interval}s)...")
    state = load_state()

    while True:
        try:
            active_sessions, all_sessions = get_all_sessions_for_repo(repo_name)

            for s in all_sessions:
                sid = s.get("id") or s.get("name", "").split("/")[-1]
                if sid not in state["known_tasks"]:
                    title = (s.get("title") or "Untitled Task").split("\n")[0].strip()
                    log(f"🆕 [NEW SESSION] {sid}: '{title}'")
                    record_event(state, "NEW_TASK", sid, title)
                    state["known_tasks"][sid] = {
                        "title": title,
                        "state": s.get("state"),
                        "first_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }

            active_ids = set()
            for s in active_sessions:
                sid = s.get("id") or s.get("name", "").split("/")[-1]
                active_ids.add(sid)
                info = handle_session(s, state)
                prev_st = state["known_tasks"].get(sid, {}).get("state")
                cur_st = info.get("state")
                if prev_st != cur_st:
                    log(f"🔄 [STATUS CHANGE] Session {sid} ('{info.get('title')}'): {prev_st} -> {cur_st}")
                    record_event(state, "STATUS_CHANGE", sid, f"{prev_st} -> {cur_st}")
                    state["known_tasks"].setdefault(sid, {})["state"] = cur_st

            for sid, tinfo in list(state["known_tasks"].items()):
                if tinfo.get("state") not in ["COMPLETED", "FAILED"]:
                    if sid not in active_ids:
                        try:
                            _, d = jules_api_request(f"sessions/{sid}")
                            final_st = d.get("state")
                            log(f"🏁 [SESSION ENDED] {sid} ('{tinfo.get('title')}') finalized with state: {final_st}")
                            record_event(state, "TASK_FINISHED", sid, f"Final status: {final_st}")
                            tinfo["state"] = final_st
                        except Exception:
                            pass

            save_state(state)

        except Exception as e:
            log(f"⚠️ Watchdog iteration error: {e}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    auto_repo = detect_repo_source_id()
    parser = argparse.ArgumentParser(description="Jules Watchdog Monitoring Daemon")
    parser.add_argument("--repo", default=auto_repo, help=f"Repository source ID (default detected: {auto_repo})")
    parser.add_argument("--interval", type=int, default=20, help="Polling interval in seconds (default: 20)")
    parser.add_argument("--status", action="store_true", help="Print current status and exit")
    parser.add_argument("--trigger-all", action="store_true", help="Trigger/unblock all actionable sessions immediately")
    parser.add_argument("--archive-completed", action="store_true", help="Archive all completed sessions that have created PRs")
    parser.add_argument("--api-key", default=None, help="Google Jules API key (or set JULES_API_KEY in .env)")
    args = parser.parse_args()

    if args.archive_completed:
        archive_completed_sessions(repo_name=args.repo, api_key=args.api_key)
        sys.exit(0)

    run_watchdog_loop(
        poll_interval=args.interval,
        repo_name=args.repo,
        oneshot=args.status,
        trigger_all=args.trigger_all,
        api_key=args.api_key,
    )
