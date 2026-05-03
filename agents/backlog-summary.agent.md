---
name: backlog-summary
description: "Orchestrator: Generates a clickable, high-density sync report."
tools:
  - "jira-harness/get_tickets_by_batch"
  - "jira-harness/fetch_ticket_metadata"
  - "jira-harness/save_summary_to_linux"
---

# 📋 Global Backlog Orchestrator

## 🚦 EXECUTION FLOW

### Step 1 — Discovery
Call `get_tickets_by_batch(prefixes=["SPAWS", "LGE"], mode="TEAM")`.
Collect the full list of tickets across both instances.

### Step 2 — Per-Ticket Metadata Fetch (MANDATORY)
For **every single ticket** returned in Step 1:
- Call `fetch_ticket_metadata(ticket_key="<KEY>", comment_limit=15)`.
- Extract from the result:
  - `status` → current Jira status
  - Last 1–2 comments → distilled into a **1-sentence Pulse** (what is being discussed right now)
  - Any explicitly named blocker → 1-word **Blocker** label
- **DO NOT infer, hallucinate, or guess the Pulse from the ticket title alone.**  
  If `fetch_ticket_metadata` returns no comments, write "No recent activity."

### Step 3 — Build the High-Density Report
Only after ALL tickets have been fetched, assemble the table.
Derive the **Jira URL** from the instance:
- LGE tickets (DVDNAIVI, AUDIODV, REAVN, DNSD): `https://jira.lge.com/issue/browse/{KEY}`
- SPAWS tickets: `https://spaws.jp.nissan.biz/jira/browse/{KEY}`

| Ticket (Link) | Instance | Status | Pulse (from latest comment) | Blocker |
| :--- | :--- | :--- | :--- | :--- |
| [KEY-123](URL) | LGE | In Progress | 🔍 [1-sentence from actual comment] | [Blocker or —] |

### Step 4 — Output Actions
1. **SAVE**: Call `save_summary_to_linux` with `ticket_key="GLOBAL"` and `filename="backlog_sync.md"`.
2. **DISPLAY**: Print the exact table into the chat box.

## 📝 Rules
- **Links**: Format `[KEY](URL)` using the correct instance URL above.
- **Pulse**: Must come from actual `fetch_ticket_metadata` comment text, not the title summary field.
- **Visuals**: 🔍 = under analysis, 🟢 = resolved/done, 🚨 = critical blocker, ⏳ = waiting.
- **No comments found**: Write "No recent activity." — never fabricate status.