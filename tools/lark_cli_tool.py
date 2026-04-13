"""Lark/Feishu CLI tool for interacting with Lark/Feishu via lark-cli.

This tool wraps the lark-cli command-line interface, providing access to
Lark/Feishu features including calendar, messaging, docs, sheets, tasks, and more.

Requires:
- lark-cli installed: npm install -g @larksuite/cli
- Authentication: automatically configured from FEISHU_APP_ID + FEISHU_APP_SECRET env vars

Tools provided:
- lark_calendar_agenda: View upcoming calendar events
- lark_calendar_events: List calendar events for a time range
- lark_im_send: Send a message to a chat
- lark_im_reply: Reply to a specific message
- lark_contact_search: Search for users by name/email/phone
- lark_doc_create: Create a new document
- lark_doc_read: Read a document's content
- lark_sheet_read: Read spreadsheet data
- lark_task_create: Create a task
- lark_task_list: List tasks
- lark_api_call: Make a raw Lark API call
- lark_auth_status: Check authentication status
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Path to lark-cli binary
_LARK_CLI_PATH = os.environ.get(
    "LARK_CLI_PATH",
    os.path.join(os.path.expanduser("~"), ".hermes", "node", "bin", "lark-cli")
)

# Default timeout for lark-cli commands (seconds)
_LARK_CLI_TIMEOUT = 30

# lark-cli config directory
_LARK_CLI_CONFIG_DIR = Path.home() / ".lark-cli"
_LARK_CLI_CONFIG_FILE = _LARK_CLI_CONFIG_DIR / "config.json"


def _check_lark_cli_available() -> bool:
    """Check if lark-cli is installed AND configured with Hermes credentials.
    
    This function first ensures lark-cli is configured using the same
    FEISHU_APP_ID and FEISHU_APP_SECRET that Hermes uses.
    """
    # First check if binary exists
    try:
        result = subprocess.run(
            [_LARK_CLI_PATH, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    
    # Ensure lark-cli is configured with Hermes credentials
    return _ensure_lark_cli_configured()


def _get_hermes_feishu_credentials() -> tuple[Optional[str], Optional[str]]:
    """Get Feishu credentials from Hermes config (env vars or config file)."""
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    
    if app_id and app_secret:
        return app_id.strip(), app_secret.strip()
    
    # Try to read from Hermes config file
    config_path = Path.home() / ".hermes" / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                config = yaml.safe_load(f)
            
            feishu_config = config.get("feishu", {})
            app_id = feishu_config.get("app_id", "")
            app_secret = feishu_config.get("app_secret", "")
            
            if app_id and app_secret:
                return app_id.strip(), app_secret.strip()
        except Exception:
            pass
    
    return None, None


def _ensure_lark_cli_configured() -> bool:
    """Ensure lark-cli is configured with Feishu credentials from Hermes.
    
    This allows single-point configuration - users only need to set
    FEISHU_APP_ID and FEISHU_APP_SECRET in Hermes, and lark-cli will
    automatically use the same credentials.
    """
    # Check if already configured
    if _LARK_CLI_CONFIG_FILE.exists():
        try:
            with open(_LARK_CLI_CONFIG_FILE) as f:
                config = json.load(f)
            if config.get("appId") and config.get("appSecret"):
                # Already configured
                return True
        except Exception:
            pass
    
    # Get credentials from Hermes
    app_id, app_secret = _get_hermes_feishu_credentials()
    
    if not app_id or not app_secret:
        logger.warning(
            "lark-cli not configured and FEISHU_APP_ID/FEISHU_APP_SECRET not set. "
            "Set these environment variables to enable lark-cli tools."
        )
        return False
    
    # Configure lark-cli with Hermes credentials
    try:
        result = subprocess.run(
            [_LARK_CLI_PATH, "config", "init",
             "--app-id", app_id,
             "--app-secret-stdin",
             "--brand", "feishu"],
            input=app_secret.encode(),
            capture_output=True,
            timeout=30
        )
        
        if result.returncode == 0:
            logger.info("lark-cli configured successfully using FEISHU_APP_ID/FEISHU_APP_SECRET")
            return True
        else:
            logger.error("Failed to configure lark-cli: %s", result.stderr.decode() if result.stderr else result.stdout.decode())
            return False
            
    except Exception as e:
        logger.error("Error configuring lark-cli: %s", e)
        return False


def _run_lark_cli(args: List[str], timeout: int = _LARK_CLI_TIMEOUT, add_format_json: bool = True) -> Dict[str, Any]:
    """Run lark-cli with given arguments and return parsed JSON output."""
    cmd = [_LARK_CLI_PATH] + args
    
    # Add format=json to ensure JSON output (but not all commands support it)
    if add_format_json and "--format" not in args and "-f" not in args:
        cmd.extend(["--format", "json"])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            return {
                "ok": False,
                "error": {
                    "type": "command_failed",
                    "message": result.stderr or result.stdout,
                    "returncode": result.returncode
                }
            }
        
        # Try to parse as JSON
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {
                "ok": True,
                "data": result.stdout
            }
            
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": {
                "type": "timeout",
                "message": f"Command timed out after {timeout} seconds",
                "command": " ".join(args)
            }
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "error": {
                "type": "not_found",
                "message": f"lark-cli not found at {_LARK_CLI_PATH}. Install with: npm install -g @larksuite/cli"
            }
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {
                "type": "exception",
                "message": str(exc)
            }
        }


# =============================================================================
# Tool Handlers
# =============================================================================

def _handle_auth_status(args: Dict[str, Any], **kwargs) -> str:
    """Check current lark-cli authentication status."""
    result = _run_lark_cli(["auth", "status"], add_format_json=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_calendar_agenda(args: Dict[str, Any], **kwargs) -> str:
    """View upcoming calendar events."""
    lookback_days = args.get("lookback_days", 7)
    result = _run_lark_cli(["calendar", "+agenda", "--lookback-days", str(lookback_days)])
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_calendar_events(args: Dict[str, Any], **kwargs) -> str:
    """List calendar events for a time range."""
    calendar_id = args.get("calendar_id", "primary")
    start_time = args.get("start_time")
    end_time = args.get("end_time")
    
    if not start_time or not end_time:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "start_time and end_time are required (Unix timestamp)"
            }
        }, ensure_ascii=False)
    
    params = json.dumps({
        "calendar_id": calendar_id,
        "start_time": start_time,
        "end_time": end_time
    })
    result = _run_lark_cli(["calendar", "events", "instance_view", "--params", params])
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_im_send(args: Dict[str, Any], **kwargs) -> str:
    """Send a message to a chat."""
    chat_id = args.get("chat_id")
    text = args.get("text")
    
    if not chat_id or not text:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "chat_id and text are required"
            }
        }, ensure_ascii=False)
    
    result = _run_lark_cli([
        "im", "+messages-send",
        "--chat-id", chat_id,
        "--text", text
    ])
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_im_reply(args: Dict[str, Any], **kwargs) -> str:
    """Reply to a specific message."""
    chat_id = args.get("chat_id")
    message_id = args.get("message_id")
    text = args.get("text")
    
    if not chat_id or not message_id or not text:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "chat_id, message_id, and text are required"
            }
        }, ensure_ascii=False)
    
    result = _run_lark_cli([
        "im", "+messages-reply",
        "--chat-id", chat_id,
        "--message-id", message_id,
        "--text", text
    ])
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_contact_search(args: Dict[str, Any], **kwargs) -> str:
    """Search for users by name, email, or phone."""
    query = args.get("query")
    
    if not query:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "query is required"
            }
        }, ensure_ascii=False)
    
    result = _run_lark_cli(["contact", "+search-user", "--query", query])
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_doc_create(args: Dict[str, Any], **kwargs) -> str:
    """Create a new document."""
    title = args.get("title", "Untitled")
    content = args.get("content", "")
    doc_type = args.get("doc_type", "doc")  # doc, sheet, bitable
    
    if doc_type == "doc":
        result = _run_lark_cli([
            "docs", "+create",
            "--title", title,
            "--markdown", content
        ])
    elif doc_type == "sheet":
        result = _run_lark_cli([
            "sheets", "+create",
            "--title", title
        ])
    elif doc_type == "bitable":
        result = _run_lark_cli([
            "base", "+create",
            "--name", title
        ])
    else:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "invalid_parameter",
                "message": f"Unsupported doc_type: {doc_type}. Use: doc, sheet, bitable"
            }
        }, ensure_ascii=False)
    
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_doc_read(args: Dict[str, Any], **kwargs) -> str:
    """Read a document's content."""
    token = args.get("token")
    
    if not token:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "token (document token) is required"
            }
        }, ensure_ascii=False)
    
    result = _run_lark_cli(["docs", "+read", "--token", token])
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_sheet_read(args: Dict[str, Any], **kwargs) -> str:
    """Read spreadsheet data."""
    token = args.get("token")
    range_ = args.get("range")  # e.g., "Sheet1!A1:C10"
    
    if not token:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "token (spreadsheet token) is required"
            }
        }, ensure_ascii=False)
    
    cmd = ["sheets", "+read", "--token", token]
    if range_:
        cmd.extend(["--range", range_])
    
    result = _run_lark_cli(cmd)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_task_create(args: Dict[str, Any], **kwargs) -> str:
    """Create a new task."""
    title = args.get("title")
    description = args.get("description", "")
    due_date = args.get("due_date")  # ISO format or Unix timestamp
    
    if not title:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "title is required"
            }
        }, ensure_ascii=False)
    
    cmd = ["task", "+create", "--title", title]
    if description:
        cmd.extend(["--description", description])
    if due_date:
        cmd.extend(["--due-date", str(due_date)])
    
    result = _run_lark_cli(cmd)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_task_list(args: Dict[str, Any], **kwargs) -> str:
    """List tasks."""
    completed = args.get("completed")
    
    cmd = ["task", "+list"]
    if completed is not None:
        cmd.extend(["--completed", str(completed).lower()])
    
    result = _run_lark_cli(cmd)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_api_call(args: Dict[str, Any], **kwargs) -> str:
    """Make a raw Lark API call."""
    method = args.get("method", "GET").upper()
    path = args.get("path")
    
    if not path:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "path is required (e.g., /open-apis/calendar/v4/calendars)"
            }
        }, ensure_ascii=False)
    
    params = args.get("params")
    data = args.get("data")
    
    cmd = ["api", method, path]
    if params:
        cmd.extend(["--params", json.dumps(params)])
    if data:
        cmd.extend(["--data", json.dumps(data)])
    
    result = _run_lark_cli(cmd, timeout=60)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_doctor(args: Dict[str, Any], **kwargs) -> str:
    """Run lark-cli health check."""
    result = _run_lark_cli(["doctor"])
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_wiki_node_create(args: Dict[str, Any], **kwargs) -> str:
    """Create a new wiki node (page in a wiki space)."""
    title = args.get("title")
    obj_type = args.get("obj_type", "docx")
    space_id = args.get("space_id", "")
    parent_node_token = args.get("parent_node_token", "")
    node_type = args.get("node_type", "origin")
    origin_node_token = args.get("origin_node_token", "")
    
    if not title:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "title is required"
            }
        }, ensure_ascii=False)
    
    cmd = ["wiki", "+node-create", "--title", title, "--obj-type", obj_type]
    
    if space_id:
        cmd.extend(["--space-id", space_id])
    if parent_node_token:
        cmd.extend(["--parent-node-token", parent_node_token])
    if node_type:
        cmd.extend(["--node-type", node_type])
    if origin_node_token:
        cmd.extend(["--origin-node-token", origin_node_token])
    
    result = _run_lark_cli(cmd)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_wiki_spaces_list(args: Dict[str, Any], **kwargs) -> str:
    """List wiki spaces accessible to the user."""
    result = _run_lark_cli(["wiki", "spaces", "list"])
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_wiki_nodes_list(args: Dict[str, Any], **kwargs) -> str:
    """List nodes in a wiki space."""
    space_id = args.get("space_id")
    
    if not space_id:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "space_id is required"
            }
        }, ensure_ascii=False)
    
    result = _run_lark_cli(["wiki", "nodes", "list", "--space-id", space_id])
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_doc_search(args: Dict[str, Any], **kwargs) -> str:
    """Search Lark docs, Wiki, and spreadsheet files."""
    query = args.get("query")
    page_size = args.get("page_size", 15)
    page_token = args.get("page_token", "")
    search_type = args.get("search_type", "")  # doc, sheet, bitable, etc.
    
    if not query:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "query is required"
            }
        }, ensure_ascii=False)
    
    cmd = ["docs", "+search", "--query", query, "--page-size", str(page_size)]
    
    if page_token:
        cmd.extend(["--page-token", page_token])
    if search_type:
        cmd.extend(["--filter", json.dumps({"type": search_type})])
    
    result = _run_lark_cli(cmd)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_doc_update(args: Dict[str, Any], **kwargs) -> str:
    """Update a Lark document's title or content."""
    token = args.get("token")
    title = args.get("title", "")
    content = args.get("content", "")
    
    if not token:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "token (document token) is required"
            }
        }, ensure_ascii=False)
    
    if not title and not content:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "At least one of title or content is required"
            }
        }, ensure_ascii=False)
    
    cmd = ["docs", "+update", "--token", token]
    
    if title:
        cmd.extend(["--title", title])
    if content:
        cmd.extend(["--markdown", content])
    
    result = _run_lark_cli(cmd)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _handle_doc_fetch(args: Dict[str, Any], **kwargs) -> str:
    """Fetch detailed content from a Lark document, including blocks structure."""
    token = args.get("token")
    
    if not token:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "missing_parameter",
                "message": "token (document token) is required"
            }
        }, ensure_ascii=False)
    
    result = _run_lark_cli(["docs", "+fetch", "--token", token])
    return json.dumps(result, ensure_ascii=False, indent=2)


# =============================================================================
# Tool Schemas
# =============================================================================

LARK_AUTH_STATUS_SCHEMA = {
    "name": "lark_auth_status",
    "description": "Check the current authentication status of lark-cli. Shows if you're logged in, available scopes, and user identity.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

LARK_CALENDAR_AGENDA_SCHEMA = {
    "name": "lark_calendar_agenda",
    "description": "View upcoming calendar events/agenda. Shows events from today onwards, including title, time, attendees, and location.",
    "parameters": {
        "type": "object",
        "properties": {
            "lookback_days": {
                "type": "integer",
                "description": "Number of days to look back for past events (default: 7)",
                "default": 7
            }
        },
        "required": []
    }
}

LARK_CALENDAR_EVENTS_SCHEMA = {
    "name": "lark_calendar_events",
    "description": "List calendar events for a specific time range. Use this to view events on a calendar between start_time and end_time.",
    "parameters": {
        "type": "object",
        "properties": {
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID (use 'primary' for primary calendar)",
                "default": "primary"
            },
            "start_time": {
                "type": "string",
                "description": "Start time as Unix timestamp (seconds)"
            },
            "end_time": {
                "type": "string",
                "description": "End time as Unix timestamp (seconds)"
            }
        },
        "required": ["start_time", "end_time"]
    }
}

LARK_IM_SEND_SCHEMA = {
    "name": "lark_im_send",
    "description": "Send a text message to a Feishu chat. Use this to send notifications or direct messages.",
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "The chat ID to send to (starts with oc_)"
            },
            "text": {
                "type": "string",
                "description": "The message text to send"
            }
        },
        "required": ["chat_id", "text"]
    }
}

LARK_IM_REPLY_SCHEMA = {
    "name": "lark_im_reply",
    "description": "Reply to a specific message in a Feishu chat thread.",
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "The chat ID containing the message"
            },
            "message_id": {
                "type": "string",
                "description": "The message ID to reply to"
            },
            "text": {
                "type": "string",
                "description": "The reply text"
            }
        },
        "required": ["chat_id", "message_id", "text"]
    }
}

LARK_CONTACT_SEARCH_SCHEMA = {
    "name": "lark_contact_search",
    "description": "Search for users by name, email, or phone number. Returns user profiles including open_id, name, email, and avatar.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (name, email, or phone)"
            }
        },
        "required": ["query"]
    }
}

LARK_DOC_CREATE_SCHEMA = {
    "name": "lark_doc_create",
    "description": "Create a new Lark document, spreadsheet, or bitable base.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Document title"
            },
            "content": {
                "type": "string",
                "description": "Initial content in Markdown format (for documents)"
            },
            "doc_type": {
                "type": "string",
                "description": "Document type: doc, sheet, or bitable",
                "enum": ["doc", "sheet", "bitable"],
                "default": "doc"
            }
        },
        "required": ["title"]
    }
}

LARK_DOC_READ_SCHEMA = {
    "name": "lark_doc_read",
    "description": "Read the content of a Lark document.",
    "parameters": {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "Document token (from document URL)"
            }
        },
        "required": ["token"]
    }
}

LARK_SHEET_READ_SCHEMA = {
    "name": "lark_sheet_read",
    "description": "Read data from a Lark spreadsheet.",
    "parameters": {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "Spreadsheet token (from spreadsheet URL)"
            },
            "range": {
                "type": "string",
                "description": "Cell range (e.g., 'Sheet1!A1:C10')"
            }
        },
        "required": ["token"]
    }
}

LARK_TASK_CREATE_SCHEMA = {
    "name": "lark_task_create",
    "description": "Create a new task in Lark.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Task title"
            },
            "description": {
                "type": "string",
                "description": "Task description"
            },
            "due_date": {
                "type": "string",
                "description": "Due date (ISO format or Unix timestamp)"
            }
        },
        "required": ["title"]
    }
}

LARK_TASK_LIST_SCHEMA = {
    "name": "lark_task_list",
    "description": "List tasks from Lark.",
    "parameters": {
        "type": "object",
        "properties": {
            "completed": {
                "type": "boolean",
                "description": "Filter by completion status"
            }
        },
        "required": []
    }
}

LARK_API_CALL_SCHEMA = {
    "name": "lark_api_call",
    "description": "Make a raw call to the Lark Open API. Use this for operations not covered by other tools. Requires knowledge of Lark API paths and parameters.",
    "parameters": {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP method",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "default": "GET"
            },
            "path": {
                "type": "string",
                "description": "API path (e.g., /open-apis/calendar/v4/calendars)"
            },
            "params": {
                "type": "object",
                "description": "Query parameters as JSON object"
            },
            "data": {
                "type": "object",
                "description": "Request body as JSON object (for POST/PUT/PATCH)"
            }
        },
        "required": ["path"]
    }
}

LARK_DOCTOR_SCHEMA = {
    "name": "lark_doctor",
    "description": "Run lark-cli health check to verify configuration, authentication, and connectivity to Lark services.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

LARK_WIKI_NODE_CREATE_SCHEMA = {
    "name": "lark_wiki_node_create",
    "description": "Create a new wiki node (page) in a Lark wiki space. Creates an empty document and adds it to the wiki hierarchy.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title of the wiki node"
            },
            "obj_type": {
                "type": "string",
                "description": "Object type: docx (default), sheet, bitable, slides, mindnote",
                "default": "docx"
            },
            "space_id": {
                "type": "string",
                "description": "Wiki space ID. Use 'my_library' for personal document library"
            },
            "parent_node_token": {
                "type": "string",
                "description": "Parent wiki node token to create under a specific parent"
            },
            "node_type": {
                "type": "string",
                "description": "Node type: origin (default) or shortcut",
                "default": "origin"
            },
            "origin_node_token": {
                "type": "string",
                "description": "Source node token when node_type=shortcut"
            }
        },
        "required": ["title"]
    }
}

LARK_WIKI_SPACES_LIST_SCHEMA = {
    "name": "lark_wiki_spaces_list",
    "description": "List all wiki spaces accessible to the user. Returns space IDs, names, and node counts.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

LARK_WIKI_NODES_LIST_SCHEMA = {
    "name": "lark_wiki_nodes_list",
    "description": "List all nodes (pages) in a wiki space.",
    "parameters": {
        "type": "object",
        "properties": {
            "space_id": {
                "type": "string",
                "description": "Wiki space ID"
            }
        },
        "required": ["space_id"]
    }
}

LARK_DOC_SEARCH_SCHEMA = {
    "name": "lark_doc_search",
    "description": "Search across Lark docs, Wiki pages, and spreadsheets. Returns matching documents with metadata.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword or phrase"
            },
            "page_size": {
                "type": "integer",
                "description": "Number of results per page (default: 15, max: 20)",
                "default": 15
            },
            "page_token": {
                "type": "string",
                "description": "Pagination token for next page"
            },
            "search_type": {
                "type": "string",
                "description": "Filter by type: doc, sheet, bitable, docx, slides, mindnote"
            }
        },
        "required": ["query"]
    }
}

LARK_DOC_UPDATE_SCHEMA = {
    "name": "lark_doc_update",
    "description": "Update a Lark document's title and/or content (Markdown). Use to modify existing documents.",
    "parameters": {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "Document token (from document URL)"
            },
            "title": {
                "type": "string",
                "description": "New document title"
            },
            "content": {
                "type": "string",
                "description": "New content in Markdown format (replaces entire document)"
            }
        },
        "required": ["token"]
    }
}

LARK_DOC_FETCH_SCHEMA = {
    "name": "lark_doc_fetch",
    "description": "Fetch detailed content from a Lark document including block structure. More detailed than lark_doc_read.",
    "parameters": {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "Document token (from document URL)"
            }
        },
        "required": ["token"]
    }
}


# =============================================================================
# Registration
# =============================================================================

from tools.registry import registry

registry.register(
    name="lark_auth_status",
    toolset="lark",
    schema=LARK_AUTH_STATUS_SCHEMA,
    handler=_handle_auth_status,
    check_fn=_check_lark_cli_available,
    emoji="📅"
)

registry.register(
    name="lark_calendar_agenda",
    toolset="lark",
    schema=LARK_CALENDAR_AGENDA_SCHEMA,
    handler=_handle_calendar_agenda,
    check_fn=_check_lark_cli_available,
    emoji="📅"
)

registry.register(
    name="lark_calendar_events",
    toolset="lark",
    schema=LARK_CALENDAR_EVENTS_SCHEMA,
    handler=_handle_calendar_events,
    check_fn=_check_lark_cli_available,
    emoji="📅"
)

registry.register(
    name="lark_im_send",
    toolset="lark",
    schema=LARK_IM_SEND_SCHEMA,
    handler=_handle_im_send,
    check_fn=_check_lark_cli_available,
    emoji="💬"
)

registry.register(
    name="lark_im_reply",
    toolset="lark",
    schema=LARK_IM_REPLY_SCHEMA,
    handler=_handle_im_reply,
    check_fn=_check_lark_cli_available,
    emoji="💬"
)

registry.register(
    name="lark_contact_search",
    toolset="lark",
    schema=LARK_CONTACT_SEARCH_SCHEMA,
    handler=_handle_contact_search,
    check_fn=_check_lark_cli_available,
    emoji="👤"
)

registry.register(
    name="lark_doc_create",
    toolset="lark",
    schema=LARK_DOC_CREATE_SCHEMA,
    handler=_handle_doc_create,
    check_fn=_check_lark_cli_available,
    emoji="📄"
)

registry.register(
    name="lark_doc_read",
    toolset="lark",
    schema=LARK_DOC_READ_SCHEMA,
    handler=_handle_doc_read,
    check_fn=_check_lark_cli_available,
    emoji="📄"
)

registry.register(
    name="lark_sheet_read",
    toolset="lark",
    schema=LARK_SHEET_READ_SCHEMA,
    handler=_handle_sheet_read,
    check_fn=_check_lark_cli_available,
    emoji="📊"
)

registry.register(
    name="lark_task_create",
    toolset="lark",
    schema=LARK_TASK_CREATE_SCHEMA,
    handler=_handle_task_create,
    check_fn=_check_lark_cli_available,
    emoji="✅"
)

registry.register(
    name="lark_task_list",
    toolset="lark",
    schema=LARK_TASK_LIST_SCHEMA,
    handler=_handle_task_list,
    check_fn=_check_lark_cli_available,
    emoji="✅"
)

registry.register(
    name="lark_api_call",
    toolset="lark",
    schema=LARK_API_CALL_SCHEMA,
    handler=_handle_api_call,
    check_fn=_check_lark_cli_available,
    emoji="🔗"
)

registry.register(
    name="lark_doctor",
    toolset="lark",
    schema=LARK_DOCTOR_SCHEMA,
    handler=_handle_doctor,
    check_fn=_check_lark_cli_available,
    emoji="🔧"
)

registry.register(
    name="lark_wiki_node_create",
    toolset="lark",
    schema=LARK_WIKI_NODE_CREATE_SCHEMA,
    handler=_handle_wiki_node_create,
    check_fn=_check_lark_cli_available,
    emoji="📚"
)

registry.register(
    name="lark_wiki_spaces_list",
    toolset="lark",
    schema=LARK_WIKI_SPACES_LIST_SCHEMA,
    handler=_handle_wiki_spaces_list,
    check_fn=_check_lark_cli_available,
    emoji="📚"
)

registry.register(
    name="lark_wiki_nodes_list",
    toolset="lark",
    schema=LARK_WIKI_NODES_LIST_SCHEMA,
    handler=_handle_wiki_nodes_list,
    check_fn=_check_lark_cli_available,
    emoji="📚"
)

registry.register(
    name="lark_doc_search",
    toolset="lark",
    schema=LARK_DOC_SEARCH_SCHEMA,
    handler=_handle_doc_search,
    check_fn=_check_lark_cli_available,
    emoji="🔍"
)

registry.register(
    name="lark_doc_update",
    toolset="lark",
    schema=LARK_DOC_UPDATE_SCHEMA,
    handler=_handle_doc_update,
    check_fn=_check_lark_cli_available,
    emoji="📝"
)

registry.register(
    name="lark_doc_fetch",
    toolset="lark",
    schema=LARK_DOC_FETCH_SCHEMA,
    handler=_handle_doc_fetch,
    check_fn=_check_lark_cli_available,
    emoji="📄"
)
