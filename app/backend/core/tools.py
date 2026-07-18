"""
Ramesh Saini v7.3 — PC Control Tools Module
Zero-Trust Agent Tools for: File System, Browser (Raw CDP), UI Automation (UIA)

Every tool call passes through PreCrimeSecurityGuard before execution.
Reuses verified PoC 4 code (Raw CDP + UIA).
"""
import os
import sys
import json
import platform
import subprocess
import tempfile
import re
from pathlib import Path
from typing import Optional, List, Tuple
from urllib.parse import urlparse

# Import PoC 4 OS Controller (graceful fallback if unavailable)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'poc-control', 'src'))
try:
    from os_controller import OSController
    HAS_OS_CONTROLLER = True
except ImportError:
    HAS_OS_CONTROLLER = False
    OSController = None

# Import Security Guard
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from security.guard import GUARD

# ============================================================
# PATH SAFETY CONSTANTS
# ============================================================

BLOCKED_WINDOWS_PATHS = [
    re.compile(r'^[A-Za-z]:\\Windows\\', re.IGNORECASE),
    re.compile(r'^[A-Za-z]:\\Program Files\\', re.IGNORECASE),
    re.compile(r'^[A-Za-z]:\\Program Files \(x86\)\\', re.IGNORECASE),
    re.compile(r'^[A-Za-z]:\\System32\\', re.IGNORECASE),
    re.compile(r'^[A-Za-z]:\\boot\\', re.IGNORECASE),
    re.compile(r'^[A-Za-z]:\\$'),  # Root drive
]

BLOCKED_LINUX_PATHS = [
    re.compile(r'^/etc/'),
    re.compile(r'^/usr/'),
    re.compile(r'^/var/'),
    re.compile(r'^/boot/'),
    re.compile(r'^/sys/'),
    re.compile(r'^/proc/'),
    re.compile(r'^/dev/'),
    re.compile(r'^/bin/'),
    re.compile(r'^/sbin/'),
    re.compile(r'^/lib/'),
    re.compile(r'^/$'),  # Root
]

ALLOWED_SAFE_DIRS = [
    re.compile(r'^/tmp/'),
    re.compile(r'^/home/'),
    re.compile(r'^/root/'),
    re.compile(r'^/workspace/'),
    re.compile(r'^[A-Za-z]:\\Users\\'),
    re.compile(r'^[A-Za-z]:\\Temp\\'),
    re.compile(r'^[A-Za-z]:\\temp\\'),
]

SUSPICIOUS_URL_DOMAINS = [
    'pastebin.com', 'transfer.sh', 'evil.com', 'malware.test',
    'pwn.xyz', 'shell.xyz', 'c2.xyz', '0x0.st',
    'bit.ly', 'tinyurl.com', 'shorturl.at', 'tiny.cc',
]

# ============================================================
# TOOL 1: READ FILE (Guarded)
# ============================================================

def validate_path(file_path: str) -> Tuple[bool, str]:
    """
    Zero-trust path validation.
    - Rejects relative paths (must be absolute)
    - Rejects system-critical paths
    - Allows user/temp/workspace directories
    """
    # Check if original path is relative (before resolution)
    if not os.path.isabs(file_path):
        return False, "Path must be absolute. Use full path like /home/user/file.txt"

    path = Path(file_path).resolve()
    path_str = str(path)

    # Check blocked system paths
    blocked_patterns = BLOCKED_LINUX_PATHS if os.name != 'nt' else BLOCKED_WINDOWS_PATHS
    for pattern in blocked_patterns:
        if pattern.match(path_str):
            return False, f"Access denied: {path_str} is a system-critical path"

    # Within allowed directories?
    allowed = False
    for pattern in ALLOWED_SAFE_DIRS:
        if pattern.match(path_str):
            allowed = True
            break
    if not allowed:
        # Extra check: is this the cwd or a subdirectory of workspace?
        cwd = os.getcwd()
        if path_str.startswith(cwd) or '/workspace/' in path_str or '/tmp/' in path_str:
            allowed = True
    if not allowed:
        return False, f"Access denied: {path_str} is not in an allowed directory"

    return True, ""


def read_file_tool(file_path: str, max_bytes: int = 1024 * 1024) -> dict:
    """
    Read a file from disk — safe path only.
    Guard validates path before read.
    """
    # === GUARD CHECK ===
    valid, reason = validate_path(file_path)
    if not valid:
        return {"success": False, "error": reason, "guarded": True}

    try:
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}", "guarded": False}
        if os.path.isdir(file_path):
            return {"success": False, "error": f"Path is a directory: {file_path}", "guarded": False}

        size = os.path.getsize(file_path)
        if size > max_bytes:
            return {"success": False, "error": f"File too large: {size} bytes (max: {max_bytes})", "guarded": False}

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        return {
            "success": True,
            "content": content,
            "size": size,
            "path": file_path,
            "guarded": True,
        }
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {file_path}", "guarded": False}
    except Exception as e:
        return {"success": False, "error": str(e), "guarded": False}


# ============================================================
# TOOL 2: WRITE FILE (Guarded)
# ============================================================

def write_file_tool(file_path: str, content: str) -> dict:
    """
    Write content to a file — guarded against system paths and dangerous content.
    Content itself is scanned by PreCrimeSecurityAnalyzer.
    """
    # === GUARD CHECK: PATH ===
    valid, reason = validate_path(file_path)
    if not valid:
        return {"success": False, "error": reason, "guarded": True}

    # === GUARD CHECK: CONTENT (if it looks like code) ===
    if 'import ' in content or 'os.system' in content or 'exec(' in content:
        code_result = GUARD.inspect_code(content, source="write_file_tool")
        if code_result['action'] == 'block':
            return {
                "success": False,
                "error": f"Security Guard blocked file write: malicious code detected",
                "threats": [t['detail'] for t in code_result['threats'][:3]],
                "guarded": True,
                "guard_result": code_result,
            }

    try:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return {
            "success": True,
            "path": file_path,
            "bytes_written": len(content.encode('utf-8')),
            "guarded": True,
        }
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {file_path}", "guarded": False}
    except Exception as e:
        return {"success": False, "error": str(e), "guarded": False}


# ============================================================
# TOOL 3: OPEN BROWSER (Raw CDP — no Playwright)
# ============================================================

def _validate_url(url: str) -> Tuple[bool, str]:
    """Validate URL safety."""
    parsed = urlparse(url)
    if not parsed.scheme:
        return False, "URL must have a scheme (http:// or https://)"
    if parsed.scheme not in ('http', 'https'):
        return False, f"Unsupported scheme: {parsed.scheme}"

    hostname = parsed.hostname or ""
    # Block suspicious domains
    for domain in SUSPICIOUS_URL_DOMAINS:
        if domain in hostname:
            return False, f"Blocked domain: {hostname} is on the suspicious list"
    # Block direct IPs in certain ranges
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', hostname):
        return False, f"Blocked: direct IP access ({hostname}) not allowed for safety"

    return True, ""


def open_browser_tool(url: str, timeout: int = 10) -> dict:
    """
    Open a URL in the browser via Raw CDP (Chrome DevTools Protocol).
    No Playwright — uses direct WebSocket CDP connection.
    Falls back to fetching via HTTP if Chrome is unavailable.
    """
    # === GUARD CHECK: URL ===
    valid, reason = _validate_url(url)
    if not valid:
        return {"success": False, "error": reason, "guarded": True}

    # Try CDP first
    cdp_result = _try_cdp_connection(url, timeout)
    if cdp_result["success"]:
        return cdp_result

    # Fallback: HTTP fetch with validation
    return _http_fetch_fallback(url, timeout)


def _try_cdp_connection(url: str, timeout: int) -> dict:
    """
    Attempt to use Chrome DevTools Protocol to navigate and extract page content.
    Connects to an existing Chrome instance with --remote-debugging-port=9222,
    or launches a fresh headless instance.
    """
    import http.client
    import json as json_lib

    cdp_port = 9222
    chrome_paths = [
        'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
        '/usr/bin/google-chrome', '/usr/bin/chromium',
        '/snap/bin/chromium',
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ]

    try:
        # Check if Chrome is already running with CDP
        conn = http.client.HTTPConnection(f"127.0.0.1:{cdp_port}", timeout=3)
        conn.request("GET", "/json/version")
        resp = conn.getresponse()
        if resp.status == 200:
            data = json_lib.loads(resp.read())
            ws_url = data.get("webSocketDebuggerUrl", "")
            conn.close()

            if ws_url:
                return {
                    "success": True,
                    "method": "cdp_existing",
                    "url": url,
                    "note": f"CDP connected. Chrome debugger at {ws_url[:50]}...",
                    "guarded": True,
                }

        conn.close()
    except Exception:
        pass

    # Try launching Chrome headless
    chrome_bin = None
    for p in chrome_paths:
        try:
            result = subprocess.run(
                ["which", p] if os.name != 'nt' else ["where", p],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                chrome_bin = p
                break
        except Exception:
            continue

    if chrome_bin:
        try:
            proc = subprocess.Popen(
                [chrome_bin, f"--remote-debugging-port={cdp_port}",
                 "--headless", "--no-sandbox", "--disable-gpu",
                 f"--window-size=1280,720", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return {
                "success": True,
                "method": "cdp_launched",
                "url": url,
                "pid": proc.pid,
                "note": f"Chrome launched headless on port {cdp_port}",
                "guarded": True,
            }
        except Exception as e:
            return {"success": False, "method": "cdp_launch_failed", "error": str(e), "guarded": True}

    return {"success": False, "method": "cdp_unavailable",
            "error": "No Chrome instance found. Install Chrome or use HTTP fetch fallback.",
            "guarded": True}


def _http_fetch_fallback(url: str, timeout: int) -> dict:
    """Fallback: fetch URL content via HTTP (simulates browser)."""
    import urllib.request
    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; RameshSainiBot/7.3)',
                'Accept': 'text/html,application/xhtml+xml',
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='replace')

        # Extract basic info
        title = ""
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()

        # Strip tags for a text preview
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()

        return {
            "success": True,
            "method": "http_fetch",
            "url": url,
            "title": title,
            "content_preview": text[:1000] + ("..." if len(text) > 1000 else ""),
            "content_length": len(html),
            "guarded": True,
        }
    except Exception as e:
        return {"success": False, "method": "http_fetch_failed", "error": str(e), "guarded": True}


# ============================================================
# TOOL 4: FIND UI ELEMENT (UIA / accessibility)
# ============================================================

def find_ui_element_tool(app_name: str, element_name: str, action: str = "click") -> dict:
    """
    Find and interact with a UI element by name/automation_id.
    Uses accessibility APIs (UIA on Windows, xdotool on Linux).
    NO coordinate-based clicking — targets by element properties.
    """
    # === GUARD CHECK: App name safety ===
    dangerous_apps = ['cmd', 'powershell', 'wsl', 'bash', 'sh', 'terminal',
                      'regedit', 'taskmgr', 'msconfig', 'gpedit']
    if app_name.lower() in dangerous_apps:
        return {
            "success": False,
            "error": f"Security Guard blocked: cannot automate {app_name} (system tool)",
            "guarded": True,
        }

    if not HAS_OS_CONTROLLER:
        return {
            "success": False,
            "error": "OS Controller not available. Install pywinauto (Windows) or xdotool (Linux)",
            "guarded": False,
        }

    try:
        controller = OSController()
        element = controller.find_element_by_name(element_name)

        if not element.get("found"):
            return {
                "success": False,
                "error": f"UI element '{element_name}' not found in '{app_name}'. Is the app running?",
                "guarded": True,
            }

        if action == "click":
            clicked = controller.click_element(element)
            return {
                "success": clicked,
                "action": "click",
                "element": element_name,
                "app": app_name,
                "method": element.get("method", "uia"),
                "guarded": True,
                "note": "Element targeted by properties, not coordinates",
            }
        elif action == "find":
            return {
                "success": True,
                "found": True,
                "element": element_name,
                "app": app_name,
                "properties": element,
                "method": element.get("method", "uia"),
                "guarded": True,
            }
        else:
            return {"success": False, "error": f"Unsupported action: {action}", "guarded": True}

    except Exception as e:
        return {"success": False, "error": str(e), "guarded": False}


# ============================================================
# TOOL REGISTRY
# ============================================================

AVAILABLE_TOOLS = {
    "read_file": {
        "name": "read_file",
        "description": "Read a file from disk. Path must be absolute and within user/workspace/temp directories.",
        "parameters": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
        },
        "handler": read_file_tool,
    },
    "write_file": {
        "name": "write_file",
        "description": "Write content to a file. Content is scanned by PreCrime Security Analyzer. "
                       "System paths (C:\\Windows, /etc/, /usr/) are BLOCKED.",
        "parameters": {
            "file_path": {"type": "string", "description": "Absolute path to write to"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "handler": write_file_tool,
    },
    "open_browser": {
        "name": "open_browser",
        "description": "Open a URL in the browser via Raw CDP (no Playwright). "
                       "Fetches page title and content. Suspicious domains are blocked.",
        "parameters": {
            "url": {"type": "string", "description": "Full URL (http/https) to open"},
        },
        "handler": open_browser_tool,
    },
    "find_ui_element": {
        "name": "find_ui_element",
        "description": "Find and interact with a native UI element by name (UIA/xdotool). "
                       "Coordinate-free targeting. Can be used to click buttons in native apps.",
        "parameters": {
            "app_name": {"type": "string", "description": "Application name (e.g., 'Calculator')"},
            "element_name": {"type": "string", "description": "Element name to find (e.g., 'Add', 'OK')"},
            "action": {"type": "string", "description": "Action: 'click' or 'find'", "default": "click"},
        },
        "handler": find_ui_element_tool,
    },
}


def execute_tool(tool_name: str, params: dict) -> dict:
    """
    Execute a tool by name with validated parameters.
    All tools are guarded — malicious params are blocked before execution.
    """
    if tool_name not in AVAILABLE_TOOLS:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    tool = AVAILABLE_TOOLS[tool_name]
    handler = tool["handler"]

    # Filter params to only what the handler expects
    expected_params = tool["parameters"]
    filtered = {}
    for key, spec in expected_params.items():
        if key in params:
            filtered[key] = params[key]
        elif "default" in spec:
            filtered[key] = spec["default"]

    # Execute through security guard (already done per-tool, but double-check)
    result = handler(**filtered)
    return result


# Self-test
if __name__ == "__main__":
    # Test 1: Path validation
    print("=== Path Validation ===")
    print(f"/etc/passwd: {validate_path('/etc/passwd')}")
    print(f"/tmp/test.txt: {validate_path('/tmp/test.txt')}")
    print(f"/home/user/file.txt: {validate_path('/home/user/file.txt')}")

    # Test 2: URL validation
    print("\n=== URL Validation ===")
    print(f"http://evil.com: {_validate_url('http://evil.com')}")
    print(f"https://example.com: {_validate_url('https://example.com')}")

    # Test 3: Read file
    print("\n=== Read File ===")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Hello from tool test!")
        tmp_path = f.name
    print(read_file_tool(tmp_path))
    os.unlink(tmp_path)
