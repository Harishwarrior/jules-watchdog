# Jules Watchdog Skill 🐕

An autonomous watchdog and monitoring skill for [Google Jules](https://jules.google/) coding sessions and repository proactive suggestions.

## Overview

`jules-watchdog` enables agentic coding assistants (e.g. Google Antigravity, Claude Code, Cursor) and standalone background processes to autonomously monitor Google Jules sessions, auto-approve plans, answer agent questions, and track execution lifecycles until terminal completion.

## Features

- ⚡ **Auto Plan Approval**: Automatically detects `AWAITING_PLAN_APPROVAL`, `isAwaitingReview: true`, or `PLANNING` states and submits approval via the AIDA Swebot API.
- 💬 **Interactive Feedback Dispatch**: Auto-responds to questions prompted by Jules (`AWAITING_USER_FEEDBACK`) to keep tasks moving forward unblocked.
- 🔄 **Continuous Lifecycle Tracking**: Polls the Jules API, logs state transitions, and records detailed event histories in `watchdog_state.json`.
- 🔑 **Automatic Token Refresh**: Transparently detects expired OAuth tokens (401) and triggers token refresh via `jules-cli`.
- 🎯 **Multi-Repo Support**: Works with any connected GitHub repository source (`--repo owner/repo`).

## Installation

### As an Antigravity / Agent Skill
Copy or submodule this repository into your project's `.agents/skills/` or `~/.gemini/config/skills/` directory:

```bash
mkdir -p .agents/skills/
git clone https://github.com/Harishwarrior/jules-watchdog.git .agents/skills/jules-watchdog
```

### Standalone CLI Daemon
You can also run the Python watchdog script directly:

```bash
# Check status once
python3 scripts/jules_watchdog.py --repo github/owner/repo --status

# Run continuous background monitoring (default: 20s interval)
python3 scripts/jules_watchdog.py --repo github/owner/repo --interval 20
```

## CLI Usage

```text
usage: jules_watchdog.py [-h] [--repo REPO] [--interval INTERVAL] [--status]

options:
  -h, --help           show this help message and exit
  --repo REPO          Repository source ID (e.g. github/owner/repo)
  --interval INTERVAL  Polling interval in seconds (default: 20)
  --status             Print current status and exit
```

## Requirements

- Python 3.8+
- `jules-cli` installed and authenticated (`jules login`)
- Linux keyring / Secret Service or system credential store

## License

MIT License. See [LICENSE](LICENSE) for details.
