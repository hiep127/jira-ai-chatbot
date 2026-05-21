import os
import re
import zipfile
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from jira import JIRA
from pydantic import BaseModel, Field

mcp = FastMCP("jira-harness")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = _PROJECT_ROOT / "jira_workspace"
AGENT_WIKI_ROOT = _PROJECT_ROOT / "wiki" / "topics"

_raw = os.getenv("JIRA_PROFILES_JSON", "[]")
try:
    _profile_list = json.loads(_raw)
except json.JSONDecodeError:
    _profile_list = []

JIRA_CONFIGS: dict[str, dict] = {
    p["name"]: {"url": p["host"], "token": p.get("token", ""), "jql": p.get("jql", "")}
    for p in _profile_list
    if p.get("name") and p.get("host")
}

_client_cache: dict[str, JIRA] = {}


def get_jira_client(profile_name: str | None = None, ticket_key: str | None = None) -> JIRA:
    if not JIRA_CONFIGS:
        raise RuntimeError("No Jira profiles configured. Add a profile in Settings and restart the app.")

    if profile_name:
        config = JIRA_CONFIGS.get(profile_name)
        if config is None:
            raise RuntimeError(f"Profile '{profile_name}' not found in JIRA_PROFILES_JSON.")
    elif ticket_key:
        prefix = ticket_key.split("-")[0].upper()
        config = JIRA_CONFIGS.get(prefix) or next(iter(JIRA_CONFIGS.values()))
    else:
        config = next(iter(JIRA_CONFIGS.values()))

    url = config["url"]
    if url not in _client_cache:
        _client_cache[url] = JIRA(
            server=url,
            token_auth=config["token"],
            options={"rest_api_version": "2"},
        )
    return _client_cache[url]


# --- INPUT SCHEMAS ---

class BatchScanArgs(BaseModel):
    prefixes: list[str] = Field(default=[], description="Profile names to scan. Empty means all configured profiles.")
    mode: str = Field(default="TEAM", description="'TEAM' or 'PERSONAL' (reserved for future use).")
    sort_by_age: bool = Field(default=True, description="True for oldest first.")
    custom_jql: str = Field(
        default="",
        description="Raw JQL string provided by the user. When non-empty, used as-is for all scanned profiles; per-profile configured JQL is ignored."
    )

class TicketMetadataArgs(BaseModel):
    ticket_key: str = Field(..., description="The Jira ticket key.")
    comment_limit: int = Field(default=15, description="Number of recent comments to fetch.")

class GrepLogsArgs(BaseModel):
    ticket_key: str = Field(..., description="The Jira ticket key.")
    pattern: str = Field(..., description="Regex or string pattern to search for.")

class ReadLogTailArgs(BaseModel):
    ticket_key: str = Field(..., description="The Jira ticket key.")
    relative_path: str = Field(..., description="Path to the log file relative to the ticket workspace.")
    lines: int = Field(default=100, description="Number of lines to read from the end.")

class FetchDataArgs(BaseModel):
    ticket_key: str = Field(..., description="The Jira ticket key to download attachments for.")

class SaveSummaryArgs(BaseModel):
    ticket_key: str = Field(..., description="The Jira ticket key.")
    filename: str = Field(..., description="Filename to save within the ticket workspace.")
    content: str = Field(..., description="Content of the file.")

class SavePatternArgs(BaseModel):
    topic_folder: str = Field(..., description="Wiki folder (e.g., 'Common_Patterns').")
    filename: str = Field(..., description="Markdown filename (e.g., 'audio_fix.md').")
    content: str = Field(..., description="The markdown content.")

class CloneTicketArgs(BaseModel):
    ticket_key: str = Field(..., description="The source Jira ticket key to clone.")
    target_project: str = Field(default="REAVN", description="The target project key in LGE.")


# --- TOOLS ---

@mcp.tool()
def get_tickets_by_batch(args: BatchScanArgs) -> str:
    """Orchestrator Tool: Scans multiple JIRA profiles using their configured JQL filters."""
    try:
        all_results = {}
        order_clause = "ORDER BY created ASC" if args.sort_by_age else "ORDER BY updated DESC"
        targets = args.prefixes if args.prefixes else list(JIRA_CONFIGS.keys())

        for prefix in targets:
            config = JIRA_CONFIGS.get(prefix)
            if not config:
                all_results[prefix] = {"error": f"Profile '{prefix}' not found in JIRA_PROFILES_JSON."}
                continue

            try:
                jira = get_jira_client(profile_name=prefix)

                if args.custom_jql:
                    jql = args.custom_jql
                else:
                    jql_base = config["jql"] or "resolution = Unresolved"
                    jql_base = re.sub(r'\s+order\s+by\s+\S.*$', '', jql_base, flags=re.IGNORECASE).strip()
                    jql = f"{jql_base} {order_clause}"

                issues = jira.search_issues(jql, maxResults=30)
                all_results[prefix] = [
                    {"key": i.key, "summary": i.fields.summary, "created": i.fields.created}
                    for i in issues
                ]
            except Exception as e:
                all_results[prefix] = {"error": str(e)}

        return json.dumps({"status": "SUCCESS", "data": all_results}, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": False}, indent=2)


@mcp.tool()
def fetch_ticket_metadata(args: TicketMetadataArgs) -> str:
    """Daily Worker Tool: Lightweight fetch of text/comments only. Instance-aware."""
    try:
        jira = get_jira_client(ticket_key=args.ticket_key)
        issue = jira.issue(args.ticket_key)
        all_comments = jira.comments(issue)
        recent = all_comments[-args.comment_limit:] if all_comments else []

        data = {
            "key": issue.key,
            "status": issue.fields.status.name,
            "summary": issue.fields.summary,
            "assignee": getattr(issue.fields.assignee, "displayName", "Unassigned"),
            "description": issue.fields.description or "No description.",
            "comments": [{"author": c.author.displayName, "body": c.body, "date": c.created} for c in recent]
        }
        return json.dumps({"status": "SUCCESS", "data": data}, indent=2)
    except Exception as e:
        retryable = "timeout" in str(e).lower() or "connection" in str(e).lower()
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": retryable}, indent=2)


@mcp.tool()
def grep_logs(args: GrepLogsArgs) -> str:
    """Recursively searches log files in the ticket workspace for a pattern."""
    try:
        ticket_dir = WORKSPACE_ROOT / args.ticket_key
        if not ticket_dir.exists():
            return json.dumps({"status": "SUCCESS", "data": "No workspace found for this ticket."}, indent=2)

        compiled = re.compile(args.pattern, re.IGNORECASE)
        matches: list[str] = []
        context_before = 2
        context_after = 2

        for file_path in ticket_dir.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                lines = file_path.read_text(errors="ignore").splitlines()
            except OSError:
                continue

            for i, line in enumerate(lines):
                if compiled.search(line):
                    start = max(0, i - context_before)
                    end = min(len(lines), i + context_after + 1)
                    block = "\n".join(
                        f"{'>' if j == i else ' '} {lines[j]}" for j in range(start, end)
                    )
                    matches.append(f"--- {file_path.name}:{i + 1} ---\n{block}")
                    if len("\n\n".join(matches)) > 8000:
                        break
            if len("\n\n".join(matches)) > 8000:
                break

        out = "\n\n".join(matches) if matches else "No matches found."
        return json.dumps({"status": "SUCCESS", "data": out[:8000]}, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": False}, indent=2)


@mcp.tool()
def read_log_tail(args: ReadLogTailArgs) -> str:
    """Reads the end of a specific log file."""
    try:
        full_path = (WORKSPACE_ROOT / args.ticket_key / args.relative_path).resolve()
        if not full_path.is_relative_to(WORKSPACE_ROOT):
            return json.dumps({"status": "ERROR", "message": "Path escape detected.", "retryable": False})

        lines = full_path.read_text(errors="ignore").splitlines()
        out = "\n".join(lines[-args.lines:])
        return json.dumps({"status": "SUCCESS", "data": out}, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": False}, indent=2)


@mcp.tool()
def fetch_and_prepare_data(args: FetchDataArgs) -> str:
    """Downloads and recursively extracts nested logs/zips for deep diagnostics."""
    try:
        import py7zr

        jira = get_jira_client(ticket_key=args.ticket_key)
        ticket_dir = WORKSPACE_ROOT / args.ticket_key
        ticket_dir.mkdir(parents=True, exist_ok=True)

        issue = jira.issue(args.ticket_key)
        for a in issue.fields.attachment:
            dest = ticket_dir / a.filename
            dest.write_bytes(a.get())

        processed_archives: set[Path] = set()
        extracted_something = True

        while extracted_something:
            extracted_something = False

            for file_path in list(ticket_dir.rglob("*")):
                if not file_path.is_file() or file_path in processed_archives:
                    continue

                fname = file_path.name.lower()
                is_zip = fname.endswith(".zip")
                is_7z = fname.endswith(".7z") or fname.endswith(".7z.001")

                if is_zip:
                    processed_archives.add(file_path)
                    try:
                        with zipfile.ZipFile(file_path) as zf:
                            zf.extractall(file_path.parent)
                        file_path.unlink()
                        extracted_something = True
                    except Exception as e:
                        print(f"Warning: Failed to extract {file_path.name} - {e}")

                elif is_7z:
                    processed_archives.add(file_path)
                    try:
                        with py7zr.SevenZipFile(file_path, mode="r") as zf:
                            zf.extractall(path=file_path.parent)
                        file_path.unlink()
                        extracted_something = True
                    except Exception as e:
                        print(f"Warning: Failed to extract {file_path.name} - {e}")

        manifest: dict[str, list] = {"bugreports": [], "driver_logs": [], "other": []}
        for p in ticket_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".log", ".txt", ".out"):
                rel = str(p.relative_to(ticket_dir))
                entry = {"name": p.name, "path": rel}
                if "bugreport" in p.name.lower():
                    manifest["bugreports"].append(entry)
                elif "driver" in p.name.lower():
                    manifest["driver_logs"].append(entry)
                else:
                    manifest["other"].append(entry)

        return json.dumps({"status": "SUCCESS", "manifest": manifest}, indent=2)
    except Exception as e:
        retryable = "timeout" in str(e).lower() or "connection" in str(e).lower()
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": retryable}, indent=2)


@mcp.tool()
def save_summary_to_linux(args: SaveSummaryArgs) -> str:
    """Writes diagnostic reports locally to the isolated ticket folder."""
    try:
        full_path = (WORKSPACE_ROOT / args.ticket_key / args.filename).resolve()
        if not full_path.is_relative_to(WORKSPACE_ROOT):
            return json.dumps({"status": "ERROR", "message": "Path traversal detected.", "retryable": False})

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(args.content, encoding="utf-8")
        return json.dumps({"status": "SUCCESS", "message": f"Saved to {full_path}"})
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": False})


@mcp.tool()
def save_pattern_to_memory(args: SavePatternArgs) -> str:
    """Saves learned patterns to the agent's localized long-term Wiki memory."""
    try:
        full_path = (AGENT_WIKI_ROOT / args.topic_folder / args.filename).resolve()
        if not full_path.is_relative_to(AGENT_WIKI_ROOT):
            return json.dumps({"status": "ERROR", "message": "Path traversal blocked. Stay in wiki bounds.", "retryable": False})

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(args.content, encoding="utf-8")
        return json.dumps({
            "status": "SUCCESS",
            "message": f"Learned pattern successfully committed to memory at {full_path}"
        })
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": False})


@mcp.tool()
def clone_ticket_from_spaws_to_lge(args: CloneTicketArgs) -> str:
    """Clones a ticket across instances, appending comments directly to the description."""
    if "SPAWS" not in JIRA_CONFIGS or "LGE" not in JIRA_CONFIGS:
        return json.dumps({
            "status": "ERROR",
            "message": "SPAWS or LGE profile not configured. Add both profiles in Settings.",
            "retryable": False,
        }, indent=2)

    try:
        source_jira = get_jira_client(profile_name="SPAWS")
        target_jira = get_jira_client(profile_name="LGE")

        issue = source_jira.issue(args.ticket_key)
        new_issue = target_jira.create_issue(
            project=args.target_project,
            summary=issue.fields.summary,
            description=issue.fields.description or "No description provided.",
            issuetype={"name": issue.fields.issuetype.name}
        )

        all_comments = source_jira.comments(issue)
        if all_comments:
            comments_text = "\n".join([
                f"[{c.created}] {c.author.displayName}:\n{c.body}\n"
                for c in all_comments
            ])
            updated_description = (
                f"{new_issue.fields.description}\n\n---\n"
                f"**Comments from {args.ticket_key}:**\n{comments_text}"
            )
            new_issue.update(description=updated_description)

        return json.dumps({
            "status": "SUCCESS",
            "source_ticket": args.ticket_key,
            "cloned_ticket_key": new_issue.key,
            "target_project": args.target_project
        }, indent=2)

    except Exception as e:
        retryable = "timeout" in str(e).lower() or "connection" in str(e).lower()
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": retryable}, indent=2)


if __name__ == "__main__":
    mcp.run()
