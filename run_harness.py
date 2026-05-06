import sys
import os
import subprocess
from typing import TypedDict
from langgraph.graph import StateGraph, END

sys.stdout.reconfigure(encoding='utf-8')

_CLAUDE_EXE = r"C:\Users\Admin\.local\bin\claude.exe"

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
                encoding='utf-8',
                errors='replace',
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
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        for line in iter(process.stdout.readline, ''):
            print(line, end='', flush=True)
            full_output += line
        process.wait()

    return full_output

def _claude_cmd(prompt: str) -> list[str]:
    return [_CLAUDE_EXE, "-p", prompt, "--dangerously-skip-permissions"]

# --- TERMINAL INPUT HELPER ---
def _ask_tty(prompt: str) -> str:
    """Read user input directly from the console device, bypassing stdin redirection."""
    tty_device = "CON" if os.name == "nt" else "/dev/tty"
    try:
        with open(tty_device, "w") as tty_out:
            tty_out.write(prompt)
            tty_out.flush()
        with open(tty_device, "r") as tty_in:
            return tty_in.readline().strip().lower()
    except Exception:
        print("\n[Non-interactive environment — auto-proceeding.]\n")
        return "y"

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
def planner_node(state: AgentState) -> dict:
    print(f"\n==============================================")
    print(f" PLANNING PHASE: /jira-planner")
    print(f"==============================================\n")
    command = f"/jira-planner Read {state['req_file']}."

    if state.get("status") == "plan_failed":
        command += f" CRITICAL: Fix these previous architectural errors: {state['feedback']}"

    stream_command(_claude_cmd(command))
    _report_plan()
    return {"status": "plan_reviewing"}

def plan_reviewer_node(state: AgentState) -> dict:
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
        answer = _ask_tty("Plan approved. Proceed to coding? [Y/n]: ")
        if answer == "n":
            print("Halted by user. Edit feature_plan.md and re-run when ready.")
            sys.exit(0)
        return {"status": "plan_approved", "feedback": ""}
    else:
        print("VERDICT: REJECTED")
        print(output.strip())
        print("=" * 48 + "\n")
        return {"status": "plan_failed", "feedback": output}

def coder_node(state: AgentState) -> dict:
    print(f"\n==============================================")
    print(f" CODING PHASE: /jira-coder (Iteration {state.get('iterations', 0) + 1})")
    print(f"==============================================\n")
    extra = f" CRITICAL: Fix these QA errors: {state['feedback']}" if state.get("status") == "code_failed" else ""

    output = stream_command(_claude_cmd(f"/jira-coder{extra}"))

    # If the skill found unresolved questions, collect answers then re-invoke.
    if "NEEDS_ANSWERS:" in output:
        raw_questions = output.split("NEEDS_ANSWERS:", 1)[1].strip().splitlines()
        questions = [q.strip() for q in raw_questions if q.strip()]
        print("\n[Coder paused: unresolved questions in plan]\n")
        answers = []
        for q in questions:
            answer = _ask_tty(f"  {q}\n  Answer: ")
            answers.append(f"{q} -> {answer}")
        answers_block = "\n".join(answers)
        stream_command(_claude_cmd(f"/jira-coder{extra} Answers to open questions:\n{answers_block}"))

    _report_git_diff()
    iters = state.get("iterations", 0) + 1
    return {"status": "qa_testing", "iterations": iters}

def qa_tester_node(state: AgentState) -> dict:
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
def route_from_plan_review(state: AgentState) -> str:
    if state["iterations"] >= 3: return "end"
    if state["status"] == "plan_failed": return "planner"
    return "coder"

def route_from_qa(state: AgentState) -> str:
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("req_file", nargs="?", default="req.md")
    parser.add_argument("--coder", action="store_true",
                        help="Skip planning phase and go straight to coding (plan already approved)")
    args = parser.parse_args()

    if not os.path.exists(args.req_file):
        print(f"Error: {args.req_file} not found. Run from the project root.")
        sys.exit(1)

    if args.coder:
        print(f"Starting Harness (coder phase) for {args.req_file}")
        state: AgentState = {"req_file": args.req_file, "feedback": "", "iterations": 0, "status": "plan_approved"}
        while state["iterations"] < 5 and state["status"] != "passed":
            state = {**state, **coder_node(state)}
            state = {**state, **qa_tester_node(state)}
            if state["status"] == "code_failed" and state["iterations"] >= 5:
                print("Max QA iterations reached.")
                break
        if state["status"] == "passed":
            print("Feature complete.")
    else:
        print(f"Starting Production Harness for {args.req_file}")
        app.invoke({"req_file": args.req_file, "iterations": 0, "feedback": "", "status": "starting"})
