# Architectural Refactor: 2026 Harness Engineering

Claude, please execute this architectural refactor. Do not ask for confirmation between steps, just execute them sequentially. We are moving our logic from Python wrappers into native Claude Skills, orchestrated by LangGraph.

## Step 1: Clean Up Old Architecture
If the directory `agents/` exists in the root of the project, completely delete it and all of its contents (e.g., `planner.py`, `coder.py`, `state.py`, `run_harness.py`). 

## Step 2: Create Native Claude Skills
Create the following directory structure and exact files. **CRITICAL:** You must include the YAML frontmatter (the lines between `---`) exactly as written so you can register these as skills.

### File 1: `.claude/skills/jira-planner/SKILL.md`
```markdown
---
name: jira-planner
description: Acts as the System Architect to draft a strict feature_plan.md based on the user's requirements.
disable-model-invocation: true
---
# System Architect (Jira Planner)

You are the System Architect for this Jira Application. Your tech stack is FastAPI (backend), Flet (frontend), and LangGraph (agent state). 

When invoked, you MUST follow this strict Standard Operating Procedure (SOP):
1. **READ_MEMORY:** Read `CLAUDE.md` to understand our global project constraints and layered architecture.
2. **CODEBASE_SCAN:** Scan the current project directories using your filesystem tools. Identify which existing files need to be modified.
3. **PLAN:** Read the user's requirements (passed in the prompt or in `req.md`).
4. **DRAFT:** Create a strict, detailed implementation plan and save it as `feature_plan.md`. 
5. **CONSTRAINT:** The plan MUST list the exact file paths to be touched. Do NOT write the final Python code.
```

### File 2: `.claude/skills/jira-plan-reviewer/SKILL.md`
```markdown
---
name: jira-plan-reviewer
description: Validates the feature_plan.md against the original requirements before any code is written.
disable-model-invocation: true
---
# Lead Engineer (Plan Reviewer)

You are the Lead Engineer. Your job is "Shift-Left Testing"—catching architectural bugs before compute time is wasted on coding.

When invoked, follow this SOP:
1. **READ:** Read `req.md` and the newly generated `feature_plan.md`.
2. **VALIDATE:** Check for architectural alignment. Does the plan correctly utilize Flet for UI and FastAPI for backend routing? Are there any missing edge cases?
3. **OUTPUT (PASS):** If the plan is perfect, output EXACTLY the word 'APPROVE'.
4. **OUTPUT (FAIL):** If the plan is flawed, output a specific, actionable list of remediation steps for the Planner to fix. Do NOT fix the plan yourself.
```

### File 3: `.claude/skills/jira-coder/SKILL.md`
```markdown
---
name: jira-coder
description: The fuzzy compiler that executes feature_plan.md and creates the Python code.
disable-model-invocation: true
---
# Developer (Jira Coder)

You are the "Fuzzy Compiler." Your job is to turn specifications into execution artifacts (Python/Flet code).

When invoked, follow this SOP:
1. **READ:** Read `feature_plan.md`.
2. **EXECUTE:** Implement the Python and UI code exactly as specified. Use your tools to read/write files.
3. **TOOL CREATION:** If you need to process a heavily nested Jira JSON payload, dynamically create a reusable Python parsing script in the `tools/` directory rather than hardcoding it into the UI.
4. **SELF-CORRECTION:** If the prompt contains previous failure feedback from the Code Reviewer, ensure those specific bugs are resolved in this pass.
```

### File 4: `.claude/skills/jira-reviewer/SKILL.md`
```markdown
---
name: jira-reviewer
description: Reviews recent git diffs against the feature plan to ensure architectural alignment.
disable-model-invocation: true
---
# QA & Code Reviewer

You are the Automated QA Reviewer. Do not write new feature code yourself.

When invoked, follow this SOP:
1. **DIFF CHECK:** Review the recent git changes and compare them against `feature_plan.md`.
2. **STATIC ANALYSIS:** Check for architectural alignment, security flaws, missing error handling (e.g., missing try/except blocks for Jira API calls), and clean code.
3. **EXECUTION:** Run the local test suite (pytest) and linters using your bash tools.
4. **OUTPUT (PASS):** If tests pass and the code perfectly matches the plan, output exactly: 'PASS'. 
5. **OUTPUT (FAIL):** If there are errors, output a specific list of remediation steps for the Coder to fix. Provide exact line numbers if possible.
```

## Step 3: Create the Orchestrator
Create `run_harness.py` in the root of the project with the exact Python code below. This acts as the factory floor, passing state between your native skills using `subprocess`.

### File 5: `run_harness.py`
```python
import sys
import os
import subprocess
from typing import TypedDict
from langgraph.graph import StateGraph, END

# 1. Shared State
class AgentState(TypedDict):
    req_file: str
    feedback: str
    iterations: int
    status: str

# 2. THE NODES (Triggering Native Claude Skills)
def planner_node(state: AgentState):
    print(f"\n--- 🏗️ PLANNING: Triggering /jira-planner ---")
    command = f"/jira-planner Read {state['req_file']}."
    if state.get("status") == "plan_failed":
        command += f" CRITICAL: Fix these previous architectural errors: {state['feedback']}"
    subprocess.run(["claude", "-p", command])
    return {"status": "plan_reviewing"}

def plan_reviewer_node(state: AgentState):
    print("\n--- 🧐 PLAN REVIEW: Triggering /jira-plan-reviewer ---")
    command = "/jira-plan-reviewer"
    result = subprocess.run(["claude", "-p", command], capture_output=True, text=True)
    output = result.stdout
    if "APPROVE" in output:
        print("✅ Plan Approved by Architect!")
        return {"status": "plan_approved", "feedback": ""}
    else:
        print(f"❌ Plan Rejected:\n{output}")
        return {"status": "plan_failed", "feedback": output}

def coder_node(state: AgentState):
    print("\n--- 💻 CODING: Triggering /jira-coder ---")
    command = "/jira-coder"
    if state.get("status") == "code_failed":
        command += f" CRITICAL: Fix these QA errors: {state['feedback']}"
    subprocess.run(["claude", "-p", command])
    iters = state.get("iterations", 0) + 1
    return {"status": "qa_testing", "iterations": iters}

def qa_tester_node(state: AgentState):
    print("\n--- 🧪 QA TESTING: Triggering /jira-reviewer ---")
    command = "/jira-reviewer"
    result = subprocess.run(["claude", "-p", command], capture_output=True, text=True)
    output = result.stdout
    if "PASS" in output:
        print("✅ QA Passed! Feature Complete.")
        return {"status": "passed", "feedback": ""}
    else:
        print(f"❌ QA Failed. Sending back to coder:\n{output}")
        return {"status": "code_failed", "feedback": output}

# 3. ROUTING LOGIC
def route_from_plan_review(state: AgentState):
    if state["iterations"] >= 3: return "end"
    if state["status"] == "plan_failed": return "planner"
    return "coder"

def route_from_qa(state: AgentState):
    if state["iterations"] >= 5: return "end"
    if state["status"] == "passed": return "end"
    return "coder"

# 4. BUILD THE GRAPH
workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_node)
workflow.add_node("plan_reviewer", plan_reviewer_node)
workflow.add_node("coder", coder_node)
workflow.add_node("qa_tester", qa_tester_node)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "plan_reviewer")
workflow.add_conditional_edges("plan_reviewer", route_from_plan_review, {"planner": "planner", "coder": "coder", "end": END})
workflow.add_edge("coder", "qa_tester")
workflow.add_conditional_edges("qa_tester", route_from_qa, {"coder": "coder", "end": END})

app = workflow.compile()

# 5. EXECUTION
if __name__ == "__main__":
    target_file = sys.argv[1] if len(sys.argv) > 1 else "req.md"
    if not os.path.exists(target_file):
        print(f"Error: {target_file} not found. Run from the project root.")
        sys.exit(1)
    print(f"🚀 Starting Production Harness for {target_file}")
    app.invoke({"req_file": target_file, "iterations": 0, "feedback": "", "status": "starting"})
```

When all files are created successfully, report back to the user that the Harness Architecture is complete and ready to execute.