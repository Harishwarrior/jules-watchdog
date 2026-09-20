---
name: jules-watchdog
description: Automated monitoring and watchdog daemon for Google Jules coding tasks and proactive suggestions. Use whenever the user wants to monitor Jules tasks, run a watchdog daemon, auto-approve Jules plans, auto-respond to Jules questions, or check Jules task completion status.
---

# Jules Watchdog Skill

This skill provides an automated watchdog system and monitoring workflow for Google Jules sessions and proactive repository suggestions (`rewardive/rewardive-mobile`).

## Capabilities

1. **Autonomous Plan Approval**: Detects when Jules pauses for plan approval (`AWAITING_PLAN_APPROVAL`, `isAwaitingReview: true`, or `PLANNING`), and automatically approves the plan to keep tasks progressing.
2. **Interactive Feedback Dispatch**: Detects questions asked by Jules (`AWAITING_USER_FEEDBACK`) and automatically answers them to unblock the agent.
3. **Continuous Lifecycle Monitoring**: Polls the Jules AIDA Swebot API, records state transitions in `watchdog_state.json`, and logs events to `watchdog.log`.
4. **Subagent Delegation**: Provides guidelines for spawning dedicated monitor subagents to track tasks without consuming the main conversation context.

---

## Quick Reference & Commands

The watchdog script is located at:
[`.agents/skills/jules-watchdog/scripts/jules_watchdog.py`](file:///var/home/harish/Developer/rewardive-mobile/.agents/skills/jules-watchdog/scripts/jules_watchdog.py)

### 1. Check Current Status (One-Shot)
```bash
python3 .agents/skills/jules-watchdog/scripts/jules_watchdog.py --status
```
Outputs total tasks tracked, active tasks, completed count, and recent event history.

### 2. Start Continuous Watchdog Daemon (Background)
To launch the watchdog daemon in the background with a 20-second polling interval:
```bash
python3 .agents/skills/jules-watchdog/scripts/jules_watchdog.py --interval 20
```

### 3. Target a Specific Repository
```bash
python3 .agents/skills/jules-watchdog/scripts/jules_watchdog.py --repo github/rewardive/rewardive-mobile --interval 15
```

---

## Technical Architecture & Jules API Reference

### Authentication
- Jules CLI stores OAuth credentials in Linux Secret Service / Keyring under:
  - **Service**: `jules-cli`
  - **Username**: `default`
- If an API call returns `401 Unauthorized`, the token is refreshed automatically by running:
  ```bash
  /home/linuxbrew/.linuxbrew/bin/jules remote list --session
  ```

### Key API Endpoints (`https://aida.googleapis.com/v1/swebot`)
- **List Tasks**: `GET https://aida.googleapis.com/v1/swebot/tasks?pageSize=100`
- **Get Task Details**: `GET https://aida.googleapis.com/v1/swebot/tasks/{task_id}`
- **List Tasks for Source**: `GET https://aida.googleapis.com/v1/swebot/sources/{encoded_source_id}/tasks`
- **Approve Plan / Send Feedback**: `POST https://aida.googleapis.com/v1/swebot/tasks/{task_id}:interact`
  ```json
  {
    "taskId": "{task_id}",
    "userActivity": {
      "planApproved": {}
    }
  }
  ```

---

## Watchdog Workflow for Agents

When requested to monitor or start Jules suggestions:

1. **Verify Jules Authentication**:
   Run `/home/linuxbrew/.linuxbrew/bin/jules remote list --session` to ensure fresh OAuth tokens.

2. **Check Current Status**:
   Run `python3 .agents/skills/jules-watchdog/scripts/jules_watchdog.py --status` to inspect active and completed tasks.

3. **Launch the Watchdog**:
   - Run the script in the background using `run_command` with `WaitMsBeforeAsync: 500`.
   - Alternatively, spawn a dedicated subagent (`invoke_subagent`) to manage the watchdog process and report updates reactively.

4. **Respond to Completion**:
   When all tasks transition to `SWEBOT_TASK_STATUS_COMPLETED` or terminal state, report summary statistics and git commit details back to the user.
