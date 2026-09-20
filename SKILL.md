---
name: jules-watchdog
description: Automated monitoring and watchdog daemon for Google Jules coding tasks and proactive suggestions. Use whenever the user wants to monitor Jules tasks, run a watchdog daemon, auto-approve Jules plans, auto-respond to Jules questions, or check Jules task completion status.
---

# Jules Watchdog

Automated monitoring and watchdog daemon for Google Jules coding tasks and repository suggestions.

## How It Works

1. **Polls Active Tasks**: Discovers tasks across connected repositories using the Jules AIDA Swebot API.
2. **Autonomous Plan Approval**: Detects when Jules pauses for plan approval (`AWAITING_PLAN_APPROVAL`, `isAwaitingReview: true`, or `PLANNING`) and auto-approves the plan.
3. **Interactive Feedback Dispatch**: Detects questions prompted by Jules (`AWAITING_USER_FEEDBACK`) and sends answers to unblock the agent.
4. **Token Management**: Automatically detects expired OAuth tokens (HTTP 401) and refreshes credentials using `jules-cli`.
5. **Lifecycle State Logging**: Tracks transitions to terminal states (`COMPLETED`, `FAILED`) and maintains detailed execution history.

## Usage

```bash
python3 scripts/jules_watchdog.py [options]
```

### Arguments

- `--status` - Print current status report for all tasks and exit.
- `--interval <seconds>` - Set polling interval for continuous background monitoring (default: `20`).
- `--repo <sourceId>` - Target repository source ID (default: `github/rewardive/rewardive-mobile`).

### Examples

**1. One-shot status check:**
```bash
python3 scripts/jules_watchdog.py --status
```

**2. Continuous background monitoring daemon:**
```bash
python3 scripts/jules_watchdog.py --interval 20
```

**3. Target a specific GitHub repository:**
```bash
python3 scripts/jules_watchdog.py --repo github/owner/repo --interval 15
```

## Output

```text
=======================================================
 Jules Watchdog Status Report: github/owner/repo
=======================================================
Total Tasks Tracked: 51
Currently Active:    0
Completed:           43
Failed / Stale:      8

No tasks currently awaiting approval or active.
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

## Present Results to User

When tasks reach terminal completion, present summary metrics to the user:
- Task ID and session URL (`https://jules.google.com/session/<taskId>`)
- Final outcome (`SWEBOT_TASK_STATUS_COMPLETED` or `SWEBOT_TASK_STATUS_FAILED`)
- Generated Git branch and commit details if changes were made.

## Troubleshooting

- **`401 Unauthorized`**: Run `jules remote list --session` in terminal to refresh OAuth token credentials in system keyring.
- **`jules binary not found`**: Ensure `jules` is installed via Homebrew (`/home/linuxbrew/.linuxbrew/bin/jules` or in system `$PATH`).
