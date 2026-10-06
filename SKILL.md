---
name: jules-watchdog
description: Automated monitoring and watchdog daemon for Google Jules coding tasks and proactive suggestions. Use whenever the user wants to monitor Jules tasks, run a watchdog daemon, auto-approve Jules plans, auto-respond to Jules questions, or check Jules task completion status.
---

# Jules Watchdog

Automated monitoring and watchdog daemon for Google Jules coding tasks and repository suggestions.

## How It Works

1. **Polls Active Sessions**: Discovers tasks across connected repositories using the official Google Jules v1alpha API (`https://jules.googleapis.com/v1alpha`) or AIDA SweBot API.
2. **Autonomous Plan Approval**: Detects when Jules pauses for plan approval (`AWAITING_PLAN_APPROVAL`) and auto-approves the plan via `:approvePlan`.
3. **Interactive Feedback Dispatch**: Detects questions prompted by Jules (`AWAITING_USER_FEEDBACK`) and sends tailored tech stack aware answers via `:sendMessage` to unblock the agent.
4. **Auto-Detects Repository & Tech Stack**: Automatically detects the current git repository source ID (e.g. `github/rewardive/rewardive-server`) and selects the appropriate verification commands (`go test`, `flutter test`, `npm test`, `pytest`).
5. **Auto-Archive Completed Sessions**: Automatically archives sessions that have successfully produced pull requests via `:archive`, keeping the repository task overview clean and clutter-free.
6. **Dual Authentication**: Supports Google Jules API Key authentication (via `JULES_API_KEY` environment variable or `--api-key` argument) as well as OAuth token credentials from `jules-cli`.
7. **Lifecycle State Logging**: Tracks transitions to terminal states (`COMPLETED`, `FAILED`) and maintains detailed execution history.

## Usage

```bash
python3 scripts/jules_watchdog.py [options]
```

### Arguments

- `--api-key <key>` - Google Jules API key (defaults to `JULES_API_KEY` environment variable or `.env`).
- `--status` - Print current status report for all tasks and exit.
- `--trigger-all` - One-shot sweep: unblock all sessions currently awaiting user feedback or plan approval immediately.
- `--archive-completed` - One-shot sweep: archive all completed sessions that have created PRs.
- `--interval <seconds>` - Set polling interval for continuous background monitoring (default: `20`).
- `--repo <sourceId>` - Target repository source ID (auto-detected from `git remote origin` if omitted).

### Examples

**1. One-shot sweep to trigger & unblock all waiting agent tasks:**
```bash
python3 scripts/jules_watchdog.py --trigger-all
```

**2. One-shot sweep to archive all completed tasks with PRs:**
```bash
python3 scripts/jules_watchdog.py --archive-completed
```

**3. One-shot status check:**
```bash
python3 scripts/jules_watchdog.py --status
```

**4. Continuous background monitoring daemon:**
```bash
python3 scripts/jules_watchdog.py --interval 20
```

**5. Explicit API Key and repository target:**
```bash
python3 scripts/jules_watchdog.py --api-key "AQ..." --repo github/rewardive/rewardive-server --trigger-all
```

## Output

```text
=======================================================
 Jules Watchdog Status Report: github/rewardive/rewardive-server
=======================================================
Total Sessions Tracked: 74
Currently Active:       28
Completed:              44
Failed / Stale:         2

Active Sessions (28):
  • [IN_PROGRESS] 15709104453732183237: Add Unit Tests for rate_limiter.go
  • [IN_PROGRESS] 12364009196675988158: Testing Improvement Task
...
=======================================================
```

## Installation

### Via Vercel Skills CLI (`skills.sh`)
```bash
npx skills add Harishwarrior/jules-watchdog
```

### Manual Installation
**Antigravity / Gemini CLI:**
```bash
git clone https://github.com/Harishwarrior/jules-watchdog.git .agents/skills/jules-watchdog
```

**Claude Code:**
```bash
git clone https://github.com/Harishwarrior/jules-watchdog.git ~/.claude/skills/jules-watchdog
```

**Cursor:**
```bash
git clone https://github.com/Harishwarrior/jules-watchdog.git .cursor/skills/jules-watchdog
```

## Authentication Setup

1. **Jules API Key (Recommended):**
   - Provide your Google Jules API key via the `JULES_API_KEY` environment variable, `.env` file, or `--api-key` CLI argument:
   ```bash
   export JULES_API_KEY="your-api-key"
   ```
2. **OAuth Token (`jules-cli`):**
   - If no API key is specified, the watchdog retrieves existing OAuth session credentials from macOS Keychain or Linux SecretStorage (`jules login`).

## Present Results to User

When tasks reach terminal completion, present summary metrics to the user:
- Task ID and session URL (`https://jules.google.com/session/<taskId>`)
- Final outcome (`COMPLETED` or `FAILED`)
- Generated Git branch and PR / commit details.
