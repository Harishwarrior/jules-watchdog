# Jules Watchdog Skill 🐕

An autonomous watchdog and monitoring skill for [Google Jules](https://jules.google/) coding sessions and repository proactive suggestions.

Compatible with [skills.sh](https://skills.sh) by Vercel Labs, Google Antigravity, Claude Code, Cursor, and GitHub Copilot.

---

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

---

## Overview

`jules-watchdog` enables AI coding agents and standalone processes to autonomously monitor Google Jules sessions, auto-approve plans, answer agent questions, and track execution lifecycles until terminal completion.

### Key Features

- ⚡ **Auto Plan Approval**: Automatically detects `AWAITING_PLAN_APPROVAL`, `isAwaitingReview: true`, or `PLANNING` states and submits approval via the AIDA Swebot API.
- 💬 **Interactive Feedback Dispatch**: Auto-responds to questions prompted by Jules (`AWAITING_USER_FEEDBACK`) to keep tasks moving forward unblocked.
- 🔄 **Continuous Lifecycle Tracking**: Polls the Jules API, logs state transitions, and records detailed event histories in `watchdog_state.json`.
- 🔑 **Automatic Token Refresh**: Transparently detects expired OAuth tokens (401) and triggers token refresh via `jules-cli`.
- 🎯 **Multi-Repo Support**: Works with any connected GitHub repository source (`--repo owner/repo`).

---

## CLI Usage

The watchdog script can also be run independently of any agent:

```bash
# Check status once
python3 scripts/jules_watchdog.py --repo github/owner/repo --status

# Run continuous background monitoring (default: 20s interval)
python3 scripts/jules_watchdog.py --repo github/owner/repo --interval 20
```

```text
usage: jules_watchdog.py [-h] [--repo REPO] [--interval INTERVAL] [--status]

options:
  -h, --help           show this help message and exit
  --repo REPO          Repository source ID (e.g. github/owner/repo)
  --interval INTERVAL  Polling interval in seconds (default: 20)
  --status             Print current status and exit
```

---

## Requirements

- Python 3.8+
- `jules-cli` installed and authenticated (`jules login`)
- Linux keyring / Secret Service or system credential store

---

## License

MIT License. See [LICENSE](LICENSE) for details.
