"""
Integration Tests for PC Control Tools (File, Browser CDP, UIA) with Zero-Trust Guard.

Tests:
1. File: read safe file → PASS
2. File: write to system path (C:\\Windows) → BLOCKED by Guard
3. Browser: open safe URL (example.com) → PASS
4. Browser: open suspicious URL (evil.com) → BLOCKED by Guard
5. UIA: find blocked app (cmd) → BLOCKED by Guard
6. Guard: validate_tool_params for safe file → VALID
7. Guard: validate_tool_params for system file path → BLOCKED
8. Agent: tool schemas bound correctly
"""
import os
import sys
import tempfile
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.tools import (
    read_file_tool, write_file_tool, open_browser_tool,
    find_ui_element_tool, validate_path, _validate_url,
    execute_tool, AVAILABLE_TOOLS
)
from core.agent import AgentManager
from security.guard import GUARD


class TestPCTools:

    # ============================================================
    # TOOL 1: READ FILE
    # ============================================================

    def test_1_read_safe_file(self):
        """Read a safe file from workspace/temp."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Hello from Ramesh Saini v7.3 PC Tools!")
            tmp_path = f.name

        try:
            result = read_file_tool(tmp_path)
            assert result["success"] == True, f"Read failed: {result.get('error')}"
            assert result["content"] == "Hello from Ramesh Saini v7.3 PC Tools!"
            assert result["guarded"] == True
        finally:
            os.unlink(tmp_path)

    def test_2_read_nonexistent_file(self):
        """Reading a nonexistent file should fail gracefully."""
        result = read_file_tool("/tmp/nonexistent_file_xyz.txt")
        assert result["success"] == False
        assert "not found" in result.get("error", "").lower()

    def test_3_read_system_path_blocked(self):
        """Reading from system path should be blocked."""
        result = read_file_tool("/etc/passwd")
        assert result["success"] == False
        assert result["guarded"] == True
        assert "denied" in result.get("error", "").lower() or "blocked" in result.get("error", "").lower()

    # ============================================================
    # TOOL 2: WRITE FILE
    # ============================================================

    def test_4_write_safe_file(self):
        """Write to a safe temp path."""
        tmp_path = "/tmp/ramesh_test_write.txt"
        try:
            result = write_file_tool(tmp_path, "Hello from PC Tools!")
            assert result["success"] == True, f"Write failed: {result.get('error')}"
            assert result["bytes_written"] > 0
            assert result["guarded"] == True

            # Verify content was written
            with open(tmp_path, 'r') as f:
                assert f.read() == "Hello from PC Tools!"
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_5_write_system_path_blocked(self):
        """Writing to system path should be blocked by Guard."""
        if os.name == 'nt':
            result = write_file_tool("C:\\Windows\\System32\\evil.exe", "malicious")
        else:
            result = write_file_tool("/etc/shadow", "hacked")

        assert result["success"] == False
        assert result["guarded"] == True
        assert "denied" in result.get("error", "").lower()

    def test_6_write_malicious_content_blocked(self):
        """Writing malicious code should be blocked by Précrime Guard."""
        tmp_path = "/tmp/ramesh_mal_test.txt"
        try:
            result = write_file_tool(tmp_path, "import os\nos.system('rm -rf /')")
            assert result["success"] == False, f"Should block malicious content: {result}"
            assert result["guarded"] == True
            assert "blocked" in result.get("error", "").lower()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_7_write_relative_path_blocked(self):
        """Relative paths should be blocked."""
        result = write_file_tool("relative/path.txt", "test")
        assert result["success"] == False
        assert result["guarded"] == True

    # ============================================================
    # TOOL 3: OPEN BROWSER (Raw CDP)
    # ============================================================

    def test_8_open_safe_url(self):
        """Open example.com — should work via HTTP fetch fallback or CDP."""
        result = open_browser_tool("https://example.com")
        assert result["success"] == True, f"Browser open failed: {result.get('error')}"
        assert result["url"] == "https://example.com"
        assert result["guarded"] == True
        # CDP mode: returns pid + note; HTTP mode: returns title + content_preview
        # Either mode is valid — just verify success
        if result["method"] == "cdp_launched":
            assert "pid" in result, f"CDP mode missing pid: {result}"
        elif result["method"] == "http_fetch":
            assert "Example" in result.get("title", ""), f"Expected 'Example' in title: {result.get('title')}"

    def test_9_open_suspicious_url_blocked(self):
        """Suspicious domain should be blocked by Guard."""
        result = open_browser_tool("http://evil.com/malware.exe")
        assert result["success"] == False
        assert result["guarded"] == True
        assert "blocked" in result.get("error", "").lower() or "suspicious" in result.get("error", "").lower()

    def test_10_open_invalid_url_format(self):
        """Invalid URL scheme should be blocked."""
        result = open_browser_tool("ftp://files.example.com")
        assert result["success"] == False
        assert result["guarded"] == True

    def test_11_open_direct_ip_blocked(self):
        """Direct IP access should be blocked."""
        # This should be blocked by validate_url before CDP/HTTP tries
        result = open_browser_tool("http://10.0.0.1:4444/command")
        assert result["success"] == False
        assert result["guarded"] == True

    # ============================================================
    # TOOL 4: FIND UI ELEMENT (UIA)
    # ============================================================

    def test_12_blocked_app_detected(self):
        """Trying to automate system tools should be blocked."""
        result = find_ui_element_tool("cmd", "Run", "click")
        assert result["success"] == False
        assert result["guarded"] == True
        assert "blocked" in result.get("error", "").lower()

    def test_13_blocked_app_powershell(self):
        """PowerShell automation should be blocked."""
        result = find_ui_element_tool("powershell", "OK", "click")
        assert result["success"] == False
        assert result["guarded"] == True

    # ============================================================
    # PATH VALIDATION
    # ============================================================

    def test_14_validate_safe_path(self):
        """Safe paths should validate."""
        valid, reason = validate_path("/tmp/test.txt")
        assert valid == True

        valid, reason = validate_path("/workspace/project/file.py")
        assert valid == True, f"Expected valid workspace path: {reason}"

    def test_15_validate_system_path(self):
        """System paths should be rejected."""
        valid, reason = validate_path("/etc/passwd")
        assert valid == False
        assert "denied" in reason.lower()

        valid, reason = validate_path("/usr/bin/python3")
        assert valid == False

        valid, reason = validate_path("/")
        assert valid == False

    def test_16_validate_relative_path(self):
        """Relative paths should be rejected."""
        valid, reason = validate_path("relative/file.txt")
        assert valid == False
        assert "absolute" in reason.lower()

    # ============================================================
    # URL VALIDATION
    # ============================================================

    def test_17_validate_safe_url(self):
        """Safe URLs should validate."""
        valid, reason = _validate_url("https://example.com")
        assert valid == True

        valid, reason = _validate_url("https://api.github.com")
        assert valid == True

    def test_18_validate_suspicious_url(self):
        """Suspicious URLs should be rejected."""
        valid, reason = _validate_url("http://pastebin.com/upload")
        assert valid == False
        assert "pastebin" in reason.lower()

        valid, reason = _validate_url("http://192.168.1.1/config")
        assert valid == False

    # ============================================================
    # GUARD TOOL PARAM VALIDATION
    # ============================================================

    def test_19_guard_validates_safe_file(self):
        """Guard should pass safe file params."""
        result = GUARD.validate_tool_params("read_file", {"file_path": "/tmp/test.txt"})
        assert result["valid"] == True

        result = GUARD.validate_tool_params("write_file", {"file_path": "/tmp/test.txt", "content": "hi"})
        assert result["valid"] == True

    def test_20_guard_validates_blocked_path(self):
        """Guard should block system file paths."""
        result = GUARD.validate_tool_params("read_file", {"file_path": "/etc/shadow"})
        assert result["valid"] == False
        assert result["blocked_reason"] == "system_path"

        result = GUARD.validate_tool_params("write_file", {"file_path": "C:\\Windows\\System32\\a.exe"})
        assert result["valid"] == False
        assert result["blocked_reason"] == "system_path"

    def test_21_guard_validates_blocked_url(self):
        """Guard should block suspicious URLs."""
        result = GUARD.validate_tool_params("open_browser", {"url": "http://bit.ly/malware"})
        assert result["valid"] == False
        assert result["blocked_reason"] == "suspicious_url"

    def test_22_guard_validates_blocked_app(self):
        """Guard should block system app automation."""
        result = GUARD.validate_tool_params("find_ui_element", {"app_name": "cmd", "element_name": "X"})
        assert result["valid"] == False
        assert result["blocked_reason"] == "blocked_app"

    # ============================================================
    # AGENT TOOL BINDINGS
    # ============================================================

    def test_23_agent_has_tool_schemas(self):
        """Agent should have tool schemas bound."""
        agent = AgentManager()
        schemas = agent.get_tool_schemas()
        assert len(schemas) >= 4, f"Expected >=4 tool schemas, got {len(schemas)}"

        names = [s['function']['name'] for s in schemas]
        assert "read_file" in names
        assert "write_file" in names
        assert "open_browser" in names
        assert "find_ui_element" in names

    def test_24_execute_tool_via_registry(self):
        """Tools should execute through the registry."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Registry test")
            tmp_path = f.name

        try:
            result = execute_tool("read_file", {"file_path": tmp_path})
            assert result["success"] == True
            assert "Registry test" in result["content"]
        finally:
            os.unlink(tmp_path)

    def test_25_write_then_read_roundtrip(self):
        """Write a file then read it back."""
        tmp_path = "/tmp/ramesh_roundtrip.txt"
        try:
            write = write_file_tool(tmp_path, "Roundtrip test content")
            assert write["success"] == True

            read = read_file_tool(tmp_path)
            assert read["success"] == True
            assert read["content"] == "Roundtrip test content"
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
