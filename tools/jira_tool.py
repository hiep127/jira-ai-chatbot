#!/home/worker/mcp-env/bin/python3
import os, zipfile, json, subprocess, shutil
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from jira import JIRA
from pydantic import BaseModel, Field

# Setup
env_path = os.path.join(os.path.dirname(__file__), "jira_server.env")
load_dotenv(env_path)

mcp = FastMCP("jira-harness")
WORKSPACE_ROOT = "/home/worker/jira_workspace"
AGENT_WIKI_ROOT = "/home/worker/Copilot_Memory/wiki/topics"

# --- MULTI-INSTANCE CONFIGURATION WITH BOUND FILTERS ---
JIRA_CONFIGS = {
    "SPAWS": {
        "url": os.getenv("CLIENT_JIRA_HOST"),
        "token": os.getenv("CLIENT_JIRA_TOKEN"),
        "filters": {
            "TEAM": (
                'assignee IN (LGEJ-LGEJ731, LGEJ-LGEJ1122, LGEJ-LGEJ140) '
                'AND resolution = Unresolved'
            ),
            "PERSONAL": 'assignee = currentUser() AND statusCategory != "Done"'
        }
    },
    "LGE": {
        "url": os.getenv("LGE_JIRA_HOST"),
        "token": os.getenv("LGE_JIRA_TOKEN"),
        "options": {"rest_api_version": "2"},
        "filters": {
            "TEAM": (
                'assignee IN (hang2.le, hiep.tran, duynp1.nguyen) '
                'AND resolution = Unresolved'
            ),
            "PERSONAL": 'assignee = currentUser() AND statusCategory != "Done"'
        }
    },
    "DEFAULT": {
        "url": os.getenv("CLIENT_JIRA_HOST"),
        "token": os.getenv("CLIENT_JIRA_TOKEN")
    }
}

_client_cache = {}
PREFIX_TO_INSTANCE = {
    "DVDNAIVI": "LGE", "AUDIODV": "LGE", "REAVN": "LGE", "DNSD": "LGE",
    "C2BST": "SPAWS", "C2LST": "SPAWS", "SPAWS": "SPAWS", "LGE": "LGE",
}

def get_jira_client(ticket_key: str = None, prefix: str = None):
    """Factory: Selects the correct JIRA instance based on ticket prefix."""
    proj_prefix = prefix or (ticket_key.split('-')[0].upper() if ticket_key else "DEFAULT")
    instance_key = PREFIX_TO_INSTANCE.get(proj_prefix, "DEFAULT")
    config = JIRA_CONFIGS.get(instance_key, JIRA_CONFIGS["DEFAULT"])
    
    url = config["url"]
    if url not in _client_cache:
        options = config.get("options", {"rest_api_version": "2"})
        _client_cache[url] = JIRA(server=url, token_auth=config["token"], options=options)
    return _client_cache[url]


# --- INPUT SCHEMAS ---

class BatchScanArgs(BaseModel):
    prefixes: list[str] = Field(default=["SPAWS", "LGE"], description="Profiles to scan.")
    mode: str = Field(default="TEAM", description="'TEAM' or 'PERSONAL'")
    sort_by_age: bool = Field(default=True, description="True for oldest first.")

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
    """Orchestrator Tool: Scans multiple JIRA instances using filters bound to each profile."""
    try:
        all_results = {}
        order_clause = "ORDER BY created ASC" if args.sort_by_age else "ORDER BY updated DESC"

        for prefix in args.prefixes:
            config = JIRA_CONFIGS.get(prefix)
            if not config:
                all_results[prefix] = {"error": f"Profile '{prefix}' not found."}
                continue

            try:
                jira = get_jira_client(prefix=prefix)
                jql_base = config["filters"].get(args.mode.upper())
                
                if args.mode.upper() == "TEAM" and not jql_base:
                    jql_base = config["filters"].get("PERSONAL")
                
                jql = f"{jql_base} {order_clause}"
                issues = jira.search_issues(jql, maxResults=30)
                
                all_results[prefix] = [
                    {"key": i.key, "summary": i.fields.summary, "created": i.fields.created} 
                    for i in issues
                ]
            except Exception as e:
                all_results[prefix] = {"error": str(e)}

        return json.dumps({"status": "SUCCESS", "scan_mode": args.mode.upper(), "data": all_results}, indent=2)
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
            "description": issue.fields.description or "No description.",
            "comments": [{"author": c.author.displayName, "body": c.body, "date": c.created} for c in recent]
        }
        return json.dumps({"status": "SUCCESS", "data": data}, indent=2)
    except Exception as e:
        retryable = "timeout" in str(e).lower() or "connection" in str(e).lower()
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": retryable}, indent=2)


@mcp.tool()
def grep_logs(args: GrepLogsArgs) -> str:
    """Recursively searches logs for a specific error/timestamp."""
    try:
        target_path = os.path.join(WORKSPACE_ROOT, args.ticket_key)
        cmd = ["grep", "-r", "-i", "-A", "2", "-B", "2", args.pattern, target_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        out = result.stdout[:8000] if result.stdout else "No matches found."
        return json.dumps({"status": "SUCCESS", "data": out}, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": False}, indent=2)


@mcp.tool()
def read_log_tail(args: ReadLogTailArgs) -> str:
    """Reads the end of a specific log file."""
    try:
        full_path = os.path.normpath(os.path.join(WORKSPACE_ROOT, args.ticket_key, args.relative_path))
        if not full_path.startswith(WORKSPACE_ROOT): 
            return json.dumps({"status": "ERROR", "message": "Path Escape detected.", "retryable": False})
        
        with open(full_path, 'r', errors='ignore') as f:
            content = f.readlines()
            out = "".join(content[-args.lines:])
            return json.dumps({"status": "SUCCESS", "data": out}, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": False}, indent=2)


@mcp.tool()
def fetch_and_prepare_data(args: FetchDataArgs) -> str:
    """Downloads and recursively extracts nested logs/zips for deep diagnostics."""
    try:
        jira = get_jira_client(ticket_key=args.ticket_key)
        ticket_dir = os.path.join(WORKSPACE_ROOT, args.ticket_key)
        os.makedirs(ticket_dir, exist_ok=True)
        
        # Download attachments directly to the ticket directory
        issue = jira.issue(args.ticket_key)
        for a in issue.fields.attachment:
            dest = os.path.join(ticket_dir, a.filename)
            with open(dest, "wb") as f: 
                f.write(a.get())
        
        # Recursive extraction logic
        processed_archives = set()
        extracted_something = True
        
        while extracted_something:
            extracted_something = False
            
            # Use list() to snapshot the directory state before we start creating/deleting files
            for file_path in list(Path(ticket_dir).rglob("*")):
                if not file_path.is_file() or str(file_path) in processed_archives:
                    continue
                    
                fname = file_path.name.lower()
                is_archive = fname.endswith(".7z.001") or (fname.endswith(".7z") and ".7z." not in fname) or fname.endswith(".zip")
                
                if is_archive:
                    processed_archives.add(str(file_path)) 
                    try:
                        # Use 7z for ALL archives. It handles Deflate64 and weird encodings natively.
                        subprocess.run(
                            ["7z", "x", str(file_path), f"-o{file_path.parent}", "-y"], 
                            check=True, 
                            capture_output=True
                        )
                        file_path.unlink() # Delete archive to save space
                        extracted_something = True # Trigger another loop to find newly revealed zips
                        
                    except subprocess.CalledProcessError as e:
                        # Prevent silent failures: log the 7z error to the console if an archive is truly corrupted
                        print(f"Warning: Failed to extract {file_path.name} - {e.stderr.decode(errors='ignore')}")
                        pass 

        # Build Manifest
        manifest = {"bugreports": [], "driver_logs": [], "other": []}
        for p in Path(ticket_dir).rglob("*"):
            if p.is_file() and p.suffix.lower() in [".log", ".txt", ".out"]:
                rel = f"./{p.relative_to(ticket_dir)}"
                if "bugreport" in p.name.lower(): manifest["bugreports"].append({"name": p.name, "path": rel})
                elif "driver" in p.name.lower(): manifest["driver_logs"].append({"name": p.name, "path": rel})
                else: manifest["other"].append({"name": p.name, "path": rel})

        return json.dumps({"status": "SUCCESS", "manifest": manifest}, indent=2)
    except Exception as e:
        retryable = "timeout" in str(e).lower() or "connection" in str(e).lower()
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": retryable}, indent=2)


@mcp.tool()
def save_summary_to_linux(args: SaveSummaryArgs) -> str:
    """Writes diagnostic reports locally to the isolated ticket folder."""
    try:
        path = os.path.normpath(os.path.join(WORKSPACE_ROOT, args.ticket_key, args.filename))
        if not path.startswith(WORKSPACE_ROOT):
            return json.dumps({"status": "ERROR", "message": "Path traversal detected.", "retryable": False})
            
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f: 
            f.write(args.content)
        return json.dumps({"status": "SUCCESS", "message": f"Saved to {path}"})
    except Exception as e: 
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": False})


@mcp.tool()
def save_pattern_to_memory(args: SavePatternArgs) -> str:
    """Saves learned patterns to the agent's localized long-term Wiki memory."""
    try:
        path = os.path.normpath(os.path.join(AGENT_WIKI_ROOT, args.topic_folder, args.filename))
        if not path.startswith(AGENT_WIKI_ROOT):
            return json.dumps({"status": "ERROR", "message": "Path traversal blocked. Stay in wiki bounds.", "retryable": False})
            
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f: 
            f.write(args.content)
            
        return json.dumps({
            "status": "SUCCESS", 
            "message": f"Learned pattern successfully committed to memory at {path}"
        })
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e), "retryable": False})


@mcp.tool()
def clone_ticket_from_spaws_to_lge(args: CloneTicketArgs) -> str:
    """Clones a ticket across instances, appending comments directly to the description."""
    try:
        source_jira = get_jira_client(prefix="SPAWS")
        target_jira = get_jira_client(prefix="LGE")
        
        issue = source_jira.issue(args.ticket_key)
        new_issue = target_jira.create_issue(
            project=args.target_project,
            summary=issue.fields.summary,
            description=issue.fields.description or "No description provided.",
            issuetype={"name": issue.fields.issuetype.name}
        )
        
        # Append comments cleanly
        all_comments = source_jira.comments(issue)
        if all_comments:
            comments_text = "\n".join([
                f"[{c.created}] {c.author.displayName}:\n{c.body}\n"
                for c in all_comments
            ])
            updated_description = f"{new_issue.fields.description}\n\n---\n**Comments from {args.ticket_key}:**\n{comments_text}"
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