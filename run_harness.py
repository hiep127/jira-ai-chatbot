import sys
import os
import subprocess
from typing import TypedDict
from langgraph.graph import StateGraph, END

sys.stdout.reconfigure(encoding='utf-8')

# claude is installed as a PowerShell script on Windows
_CLAUDE_PS1 = r"C:\Users\Admin\AppData\Roaming\npm\claude.ps1"

# 1. Shared State
class AgentState(TypedDict):
    req_file: str
    feedback: str
    iterations: int
    status: str

# --- HELPER FUNCTION ---
def stream_command(command: list[str]) -> str:
    """Streams output directly to the TTY, bypassing Claude Code's spinner capture."""
    
    # Check if we are on Windows or Unix/Mac to get the correct terminal device
    tty_device = "CON" if os.name == "nt" else "/dev/tty"
    
    full_output = ""
    try:
        # Open the raw terminal device
        with open(tty_device, "w") as tty:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Read line by line and force write to the TTY
            for line in iter(process.stdout.readline, ''):
                tty.write(line)
                tty.flush() # Force it to appear instantly
                full_output += line
                
            process.stdout.close()
            process.wait()
    except Exception as e:
        # Fallback if TTY access fails
        print(f"\n[Warning: TTY direct write failed: {e}. Falling back to standard print.]")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in iter(process.stdout.readline, ''):
            print(line, end='', flush=True)
            full_output += line
        process.wait()

    return full_output

def _claude_cmd(prompt: str) -> list[str]:
    return ["powershell", "-ExecutionPolicy", "Bypass", "-File", _CLAUDE_PS1, "-p", prompt, "--dangerously-skip-permissions"]

# --- STEP REPORTERS ---
def _report_plan() -> None:
    print("\n" + "=" * 48)
    print(" STEP REPORT: feature_plan.md")
    print("=" * 48)
    if os.path.exists("feature_plan.md"):
        with open("feature_plan.md", "r", encoding="utf-8") as f:
            print(f.read())
    else:
        print("(feature_plan.md was not created)")
    print("=" * 48 + "\n")

def _report_git_diff() -> None:
    print("\n" + "=" * 48)
    print(" STEP REPORT: Files changed by coder")
    print("=" * 48)
    result = subprocess.run(["git", "diff", "--stat", "HEAD"], capture_output=True, text=True)
    print(result.stdout.strip() or "(no tracked file changes)")
    print("=" * 48 + "\n")

# --- 2. THE NODES ---
def planner_node(state: AgentState):
    print(f"\n==============================================")
    print(f" PLANNING PHASE: /jira-planner")
    print(f"==============================================\n")
    command = f"/jira-planner Read {state['req_file']}."

    if state.get("status") == "plan_failed":
        command += f" CRITICAL: Fix these previous architectural errors: {state['feedback']}"

    stream_command(_claude_cmd(command))
    _report_plan()
    return {"status": "plan_reviewing"}

def plan_reviewer_node(state: AgentState):
    print(f"\n==============================================")
    print(f" PLAN REVIEW PHASE: /jira-plan-reviewer")
    print(f"==============================================\n")

    output = stream_command(_claude_cmd("/jira-plan-reviewer"))

    print("\n" + "=" * 48)
    print(" STEP REPORT: Plan Review Verdict")
    print("=" * 48)
    if "APPROVE" in output:
        print("VERDICT: APPROVED")
        print("=" * 48 + "\n")
        _report_plan()
        try:
            answer = input("Plan approved. Proceed to coding? [Y/n]: ").strip().lower()
        except EOFError:
            answer = "y"
        if answer == "n":
            print("Halted by user. Edit feature_plan.md and re-run when ready.")
            sys.exit(0)
        return {"status": "plan_approved", "feedback": ""}
    else:
        print("VERDICT: REJECTED")
        print(output.strip())
        print("=" * 48 + "\n")
        return {"status": "plan_failed", "feedback": output}

def coder_node(state: AgentState):
    print(f"\n==============================================")
    print(f" CODING PHASE: /jira-coder (Iteration {state.get('iterations', 0) + 1})")
    print(f"==============================================\n")
    command = "/jira-coder"
    if state.get("status") == "code_failed":
        command += f" CRITICAL: Fix these QA errors: {state['feedback']}"

    stream_command(_claude_cmd(command))
    _report_git_diff()
    iters = state.get("iterations", 0) + 1
    return {"status": "qa_testing", "iterations": iters}

def qa_tester_node(state: AgentState):
    print(f"\n==============================================")
    print(f" QA TESTING PHASE: /jira-reviewer")
    print(f"==============================================\n")

    output = stream_command(_claude_cmd("/jira-reviewer"))

    print("\n" + "=" * 48)
    print(" STEP REPORT: QA Verdict")
    print("=" * 48)
    if "PASS" in output:
        print("VERDICT: PASS — Feature Complete.")
        print("=" * 48 + "\n")
        return {"status": "passed", "feedback": ""}
    else:
        print("VERDICT: FAIL")
        print(output.strip())
        print("=" * 48 + "\n")
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
    print(f"Starting Production Harness for {target_file}")
    app.invoke({"req_file": target_file, "iterations": 0, "feedback": "", "status": "starting"})
