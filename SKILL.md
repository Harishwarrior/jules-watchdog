---
name: jules-watchdog
description: Automated monitoring and watchdog daemon for Google Jules coding tasks and proactive suggestions. Use whenever the user wants to monitor Jules tasks, run a watchdog daemon, auto-approve Jules plans, auto-respond to Jules questions, or check Jules task completion status.
---

# Jules Watchdog

Automated monitoring and watchdog daemon for Google Jules coding tasks and repository suggestions.

## How It Works

1. **Polls Active Sessions**: Discovers tasks across connected repositories using the official Google Jules v1alpha API (`https://jules.googleapis.com/v1alpha`).
2. **Autonomous Plan Approval**: Detects when Jules pauses for plan approval (`AWAITING_PLAN_APPROVAL`) and auto-approves the plan via `:approvePlan`.
3. **Interactive Feedback Dispatch**: Detects questions prompted by Jules (`AWAITING_USER_FEEDBACK`) and sends answers via `:sendMessage` to unblock the agent.
4. **Dual Authentication**: Supports Google Jules API Key authentication (via `JULES_API_KEY` environment variable or `--api-key` argument) as well as OAuth token credentials from `jules-cli`.
5. **Lifecycle State Logging**: Tracks transitions to terminal states (`COMPLETED`, `FAILED`) and maintains detailed execution history.

## Usage

```bash
python3 scripts/jules_watchdog.py [options]
```

### Arguments

- `--api-key <key>` - Google Jules API key (defaults to `JULES_API_KEY` environment variable).
- `--status` - Print current status report for all tasks and exit.
- `--interval <seconds>` - Set polling interval for continuous background monitoring (default: `20`).
- `--repo <sourceId>` - Target repository source ID (default: `github/rewardive/rewardive-mobile`).

### Examples

**1. One-shot status check (using API Key):**
```bash
export JULES_API_KEY="your-jules-api-key"
python3 scripts/jules_watchdog.py --status
```
or via argument:
```bash
python3 scripts/jules_watchdog.py --api-key "your-jules-api-key" --status
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
Total Sessions Tracked: 51
Currently Active:       0
Completed:              43
Failed / Stale:         8

No sessions currently active or awaiting approval.
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
   - Provide your Google Jules API key via the `JULES_API_KEY` environment variable or the `--api-key` CLI argument.
   ```bash
   export JULES_API_KEY="your-api-key"
   ```
2. **OAuth Token (`jules-cli`):**
   - If no API key is specified, the watchdog retrieves existing OAuth session credentials from macOS Keychain or Linux SecretStorage (`jules login`).

## Present Results to User

When tasks reach terminal completion, present summary metrics to the user:
- Task ID and session URL (`https://jules.google.com/session/<taskId>`)
- Final outcome (`COMPLETED` or `FAILED`)
- Generated Git branch and commit details if changes were made.

## Troubleshooting

- **`No Jules credentials found` / `401 Unauthorized`**: Set the `JULES_API_KEY` environment variable, pass `--api-key`, or authenticate via `jules login`.
- **`jules binary not found`**: Ensure `jules` is installed via Homebrew (`/home/linuxbrew/.linuxbrew/bin/jules` or in system `$PATH`) if using OAuth fallback.
