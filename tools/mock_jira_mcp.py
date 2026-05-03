"""Mock Jira MCP server.

Exposes the same 8 tool signatures as tools/jira_tool.py but returns
hardcoded dummy JSON so the agent can be tested without VPN or real credentials.
Run standalone: python tools/mock_jira_mcp.py
"""
import json

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("mock-jira-harness")


# --- INPUT SCHEMAS (identical to jira_tool.py) ---

_FIELD_MAP = {"Project": "project", "Assignee": "assignee", "Status": "status"}


class BatchScanArgs(BaseModel):
    prefixes:    list[str]             = Field(default=["SPAWS", "LGE"], description="Profiles to scan.")
    mode:        str                   = Field(default="TEAM", description="'TEAM' or 'PERSONAL'")
    sort_by_age: bool                  = Field(default=True, description="True for oldest first.")
    parent_link: str                   = Field(default="", description="Parent epic/issue link to scope the query.")
    filters:     dict[str, list[str]]  = Field(default_factory=dict, description="JQL filter map, e.g. {'Status': ['In Progress', 'Open']}.")


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


# --- MOCK TOOLS ---

@mcp.tool()
def get_tickets_by_batch(args: BatchScanArgs) -> str:
    """Orchestrator Tool: Scans multiple JIRA instances using filters bound to each profile."""
    jql_parts: list[str] = []

    if args.parent_link:
        jql_parts.append(f'"Epic Link" = "{args.parent_link}"')

    for field, values in args.filters.items():
        if not values:
            continue
        jql_key = _FIELD_MAP.get(field, field.lower())
        if len(values) == 1:
            jql_parts.append(f'{jql_key} = "{values[0]}"')
        else:
            val_str = ", ".join(f'"{v}"' for v in values)
            jql_parts.append(f"{jql_key} IN ({val_str})")

    jql_string = " AND ".join(jql_parts) or "(no additional filters)"

    data: dict = {}
    for prefix in args.prefixes:
        if prefix == "SPAWS":
            data[prefix] = [
                {"key": "C2BST-101", "summary": "[MOCK] Audio stuttering on HDMI output", "created": "2025-01-10T09:00:00.000+0000"},
                {"key": "C2BST-102", "summary": "[MOCK] Bluetooth pairing fails after firmware update", "created": "2025-01-12T14:30:00.000+0000"},
            ]
        elif prefix == "LGE":
            data[prefix] = [
                {"key": "AUDIODV-55", "summary": "[MOCK] Volume normalization regression in v4.2", "created": "2025-01-08T11:00:00.000+0000"},
                {"key": "DNSD-210", "summary": "[MOCK] Network discovery fails on dual-NIC setup", "created": "2025-01-15T08:45:00.000+0000"},
            ]
        else:
            data[prefix] = []

    return json.dumps({
        "status":      "SUCCESS",
        "scan_mode":   args.mode.upper(),
        "jql_applied": jql_string,
        "data":        data,
    }, indent=2)


@mcp.tool()
def fetch_ticket_metadata(args: TicketMetadataArgs) -> str:
    """Daily Worker Tool: Lightweight fetch of text/comments only. Instance-aware."""
    data = {
        "key": args.ticket_key,
        "status": "In Progress",
        "summary": f"[MOCK] Summary for {args.ticket_key}",
        "description": (
            f"This is a mock description for ticket {args.ticket_key}.\n\n"
            "Steps to reproduce:\n1. Open the app.\n2. Navigate to Settings.\n3. Observe the crash."
        ),
        "comments": [
            {
                "author": "Mock Engineer",
                "body": "Reproduced on build 4.2.1. Looks like a null-pointer in AudioService.init().",
                "date": "2025-01-13T10:15:00.000+0000",
            },
            {
                "author": "Mock Lead",
                "body": "Assigned to audio team. Please attach logcat output.",
                "date": "2025-01-14T09:00:00.000+0000",
            },
        ],
    }
    return json.dumps({"status": "SUCCESS", "data": data}, indent=2)


@mcp.tool()
def grep_logs(args: GrepLogsArgs) -> str:
    """Recursively searches logs for a specific error/timestamp."""
    out = (
        f"mock_log.txt:42:  ERROR AudioService: {args.pattern} — NullPointerException at init()\n"
        f"mock_log.txt:43:  STACK: com.example.audio.AudioService.init(AudioService.java:42)\n"
        f"mock_log.txt:44:  STACK: com.example.main.MainActivity.onCreate(MainActivity.java:87)\n"
    )
    return json.dumps({"status": "SUCCESS", "data": out}, indent=2)


@mcp.tool()
def read_log_tail(args: ReadLogTailArgs) -> str:
    """Reads the end of a specific log file."""
    out = (
        "2025-01-13 10:14:55 DEBUG  AudioService: Initializing...\n"
        "2025-01-13 10:14:55 DEBUG  AudioService: Loading config from /etc/audio.conf\n"
        "2025-01-13 10:14:56 ERROR  AudioService: Failed to acquire audio focus\n"
        "2025-01-13 10:14:56 ERROR  AudioService: NullPointerException at AudioManager.requestFocus\n"
        "2025-01-13 10:14:56 FATAL  Process terminated\n"
    )
    return json.dumps({"status": "SUCCESS", "data": out}, indent=2)


@mcp.tool()
def fetch_and_prepare_data(args: FetchDataArgs) -> str:
    """Downloads and recursively extracts nested logs/zips for deep diagnostics."""
    manifest = {
        "bugreports": [{"name": "bugreport-2025-01-13.txt", "path": "./bugreport-2025-01-13.txt"}],
        "driver_logs": [{"name": "audio_driver.log", "path": "./audio_driver.log"}],
        "other": [{"name": "system.log", "path": "./system.log"}],
    }
    return json.dumps({"status": "SUCCESS", "manifest": manifest}, indent=2)


@mcp.tool()
def save_summary_to_linux(args: SaveSummaryArgs) -> str:
    """Writes diagnostic reports locally to the isolated ticket folder."""
    return json.dumps({
        "status": "SUCCESS",
        "message": f"(mock) Saved '{args.filename}' for ticket {args.ticket_key}.",
    })


@mcp.tool()
def save_pattern_to_memory(args: SavePatternArgs) -> str:
    """Saves learned patterns to the agent's localized long-term Wiki memory."""
    return json.dumps({
        "status": "SUCCESS",
        "message": f"(mock) Pattern '{args.filename}' committed to wiki/{args.topic_folder}.",
    })


@mcp.tool()
def clone_ticket_from_spaws_to_lge(args: CloneTicketArgs) -> str:
    """Clones a ticket across instances, appending comments directly to the description."""
    return json.dumps({
        "status": "SUCCESS",
        "source_ticket": args.ticket_key,
        "cloned_ticket_key": "REAVN-999",
        "target_project": args.target_project,
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
