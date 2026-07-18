"""
Ramesh Saini v7.3 — Ironclad Security Guard
Expanded for PC Control Tools: validates tool parameters,
file paths, URLs, and app names before any execution.
"""
import sys
import os
import json
import re
from typing import Optional, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'poc-security', 'src'))
from precrime_analyzer import PreCrimeSecurityAnalyzer


# ============================================================
# TOOL PARAMETER BLOCKING RULES
# ============================================================

BLOCKED_FILE_PATHS = [
    re.compile(r'^[A-Za-z]:\\Windows\\', re.IGNORECASE),
    re.compile(r'^[A-Za-z]:\\System32\\', re.IGNORECASE),
    re.compile(r'^[A-Za-z]:\\boot\\', re.IGNORECASE),
    re.compile(r'^[A-Za-z]:\\$'),
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
    re.compile(r'^/$'),
]

SUSPICIOUS_URL_PATTERNS = [
    re.compile(r'bit\.ly|tinyurl|shorturl|pastebin|transfer\.sh'),
    re.compile(r'^\d+\.\d+\.\d+\.\d+:\d+'),  # IP:port direct
    re.compile(r'\.(exe|dll|vbs|ps1|bat|sh|bin|scr|jar)$', re.IGNORECASE),
]

BLOCKED_APP_NAMES = [
    'cmd', 'powershell', 'pwsh', 'wsl', 'bash', 'sh', 'zsh',
    'regedit', 'regedt32', 'taskmgr', 'msconfig', 'gpedit.msc',
    'compmgmt', 'devmgmt', 'diskmgmt', 'services.msc',
    'secpol.msc', 'gpedit', 'mmc', 'explorer',
]


class SecurityGuard:
    """
    The Ironclad Security Gate.
    Sits between LLM output and code execution.
    Now expanded to validate tool parameters for PC Control Tools.
    """

    def __init__(self, block_threshold: int = 6):
        self.analyzer = PreCrimeSecurityAnalyzer(block_threshold=block_threshold)
        self._block_count = 0
        self._pass_count = 0

    # ============================================================
    # CODE INSPECTION (from PoC 5)
    # ============================================================

    def inspect_code(self, code: str, source: str = "llm") -> dict:
        result = self.analyzer.analyze(code)
        if result['blocked']:
            self._block_count += 1
            action = 'block'
        elif result['threat_count'] > 0:
            action = 'warn'
        else:
            self._pass_count += 1
            action = 'allow'
        return {
            'safe': result['safe'],
            'blocked': result['blocked'],
            'threats': result['threats'],
            'score': result['score'],
            'threat_count': result['threat_count'],
            'action': action,
            'source': source,
            'analyzer': 'PreCrimeSecurityAnalyzer v7.3',
        }

    # ============================================================
    # TOOL PARAMETER VALIDATION
    # ============================================================

    def validate_tool_params(self, tool_name: str, params: dict) -> dict:
        """
        Validate tool parameters before execution.
        Returns {'valid': bool, 'error': str, 'blocked_reason': str}.
        """
        if tool_name == "read_file" or tool_name == "write_file":
            return self._validate_file_params(tool_name, params)
        elif tool_name == "open_browser":
            return self._validate_url_params(params)
        elif tool_name == "find_ui_element":
            return self._validate_uia_params(params)
        else:
            return {"valid": True, "error": None}

    def _validate_file_params(self, tool_name: str, params: dict) -> dict:
        file_path = params.get("file_path", "")
        if not file_path:
            return {"valid": False, "error": "file_path is required", "blocked_reason": "missing_param"}
        if not os.path.isabs(file_path):
            # Also catch Windows-style absolute paths on Linux (e.g., C:\Windows\...)
            if os.name != 'nt' and file_path[1:3] in (':\\', ':/'):
                is_windows_abs = True
            else:
                return {"valid": False, "error": "file_path must be absolute", "blocked_reason": "relative_path"}
        else:
            is_windows_abs = False

        # Check blocked system paths (handle Windows paths on Linux too)
        for pattern in BLOCKED_FILE_PATHS:
            if pattern.match(file_path):
                self._block_count += 1
                return {
                    "valid": False,
                    "error": f"Access denied: {file_path} is a blocked system path",
                    "blocked_reason": "system_path",
                    "matched_pattern": pattern.pattern,
                }

        # For write_file, also scan content
        if tool_name == "write_file" and "content" in params:
            content = params["content"]
            if 'import os' in content or 'os.system' in content:
                code_result = self.inspect_code(content, source="write_file_guard")
                if code_result['action'] == 'block':
                    self._block_count += 1
                    return {
                        "valid": False,
                        "error": "File content blocked by PreCrime Security Analyzer",
                        "blocked_reason": "malicious_content",
                        "threats": [t['detail'] for t in code_result['threats'][:3]],
                    }

        self._pass_count += 1
        return {"valid": True, "error": None}

    def _validate_url_params(self, params: dict) -> dict:
        url = params.get("url", "")
        if not url.startswith(("http://", "https://")):
            return {"valid": False, "error": "URL must start with http:// or https://", "blocked_reason": "invalid_scheme"}

        for pattern in SUSPICIOUS_URL_PATTERNS:
            if pattern.search(url):
                self._block_count += 1
                return {
                    "valid": False,
                    "error": f"URL blocked by security policy: {url[:60]}...",
                    "blocked_reason": "suspicious_url",
                    "matched_pattern": pattern.pattern,
                }

        self._pass_count += 1
        return {"valid": True, "error": None}

    def _validate_uia_params(self, params: dict) -> dict:
        app_name = params.get("app_name", "").lower()
        if app_name in BLOCKED_APP_NAMES:
            self._block_count += 1
            return {
                "valid": False,
                "error": f"Cannot automate {app_name}: system tool blocked",
                "blocked_reason": "blocked_app",
            }

        self._pass_count += 1
        return {"valid": True, "error": None}

    # ============================================================
    # STATS
    # ============================================================

    def get_stats(self) -> dict:
        return {
            'blocks': self._block_count,
            'passes': self._pass_count,
            'total': self._block_count + self._pass_count,
        }


# Singleton instance
GUARD = SecurityGuard()
