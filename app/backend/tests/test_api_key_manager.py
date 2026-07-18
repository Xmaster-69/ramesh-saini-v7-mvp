"""
Tests for the API Key Manager — secure key storage, validation, discovery.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.api_key_manager import APIKeyManager


class TestAPIKeyManager:

    @pytest.fixture
    def km(self):
        return APIKeyManager()

    def test_1_discover_from_env_empty(self, km):
        """With no keys set, discover returns 0."""
        # Save env
        saved = {}
        for var in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY",
                     "GEMINI_API_KEY", "MISTRAL_API_KEY"]:
            saved[var] = os.environ.get(var, "")
            if var in os.environ:
                del os.environ[var]

        try:
            count = km.discover_from_env()
            assert count == 0, f"Expected 0 discovered keys, got {count}"
            assert km.get_configured_count() == 0
        finally:
            for var, val in saved.items():
                if val:
                    os.environ[var] = val

    def test_2_discover_with_mock_keys(self, km):
        """With mock keys set, discover should find them."""
        saved = {}
        for var in ["OPENAI_API_KEY", "GROQ_API_KEY"]:
            saved[var] = os.environ.get(var, "")

        os.environ["OPENAI_API_KEY"] = "sk-test-mock-key-1234567890"
        os.environ["GROQ_API_KEY"] = "gsk_test_mock_groq_key_12345678"

        try:
            km.keys = {}  # Reset
            count = km.discover_from_env()
            assert count >= 2, f"Expected >=2 discovered keys, got {count}"
        finally:
            for var, val in saved.items():
                if val:
                    os.environ[var] = val
                else:
                    del os.environ[var]

    def test_3_get_key_returns_none_when_unset(self, km):
        """Getting key for unconfigured service returns None."""
        saved = os.environ.get("DEEPSEEK_API_KEY", "")
        if "DEEPSEEK_API_KEY" in os.environ:
            del os.environ["DEEPSEEK_API_KEY"]

        try:
            key = km.get_key("deepseek")
            assert key is None or key == ""
        finally:
            if saved:
                os.environ["DEEPSEEK_API_KEY"] = saved

    def test_4_get_key_returns_value_when_set(self, km):
        """Getting key for configured service returns the key."""
        saved = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = "sk-test-real-key-67890abcdef"

        try:
            key = km.get_key("openai")
            assert key == "sk-test-real-key-67890abcdef"
        finally:
            if saved:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                del os.environ["OPENAI_API_KEY"]

    def test_5_set_key_validates_format(self, km):
        """Setting a key with invalid format should fail."""
        result = km.set_key("openai", "too-short")
        assert result == False, "Should reject too-short key"

        result = km.set_key("openai", "invalid-format-no-sk-prefix")
        assert result == False, "Should reject key without sk- prefix"

    def test_6_set_key_valid_format(self, km):
        """Setting a properly formatted key should succeed."""
        result = km.set_key("openai", "sk-valid-key-1234567890abcdef")
        assert result == True, "Should accept properly formatted key"

        entry = km.keys.get("openai")
        assert entry is not None
        assert entry.is_configured == True
        assert entry.is_valid == True
        assert "sk-" in entry.key_preview

    def test_7_key_preview_obfuscation(self, km):
        """Key preview should show only first/last chars."""
        preview = km._preview_key("sk-test-key-1234567890abcdef")
        assert "sk-tes" in preview
        assert "cdef" in preview
        assert "1234567890abcdef" not in preview  # Full key should not be visible

    def test_8_usage_tracking(self, km):
        """API call usage should be tracked."""
        saved = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = "sk-tes...cdef"

        try:
            # Need to discover first to register the service
            km.keys = {}
            km.discover_from_env()
            
            # Make a few calls
            for _ in range(3):
                km.get_key("openai")

            status = km.get_status()
            assert "openai" in status, f"openai missing from status: {list(status.keys())}"
            assert status["openai"]["usage_count"] == 3, "Should track 3 calls"
        finally:
            if saved:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                del os.environ["OPENAI_API_KEY"]

    def test_9_get_status_structure(self, km):
        """Status endpoint should return correct structure for all services."""
        # First discover to populate keys
        saved = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = "sk-tes...cdef"
        km.keys = {}
        km.discover_from_env()

        try:
            status = km.get_status()
            assert isinstance(status, dict)
            assert len(status) > 0, "Status should have entries"

            # Check structure of at least one entry
            first_key = list(status.keys())[0]
            entry = status[first_key]
            assert "preview" in entry
            assert "configured" in entry
            assert "valid" in entry
            assert "usage_count" in entry
        finally:
            if saved:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                del os.environ["OPENAI_API_KEY"]

    def test_10_get_missing_services(self, km):
        """Should list services without configured keys."""
        saved = {}
        for var in ["OPENAI_API_KEY", "GROQ_API_KEY"]:
            saved[var] = os.environ.get(var, "")

        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
        if "GROQ_API_KEY" in os.environ:
            del os.environ["GROQ_API_KEY"]

        try:
            km.keys = {}
            km.discover_from_env()
            missing = km.get_missing_services()
            assert len(missing) >= 2, f"Expected >=2 missing services, got {len(missing)}"
        finally:
            for var, val in saved.items():
                if val:
                    os.environ[var] = val

    def test_11_rate_limit_tracking(self, km):
        """Rate limit tracking should record request timestamps."""
        saved = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = "sk-tes...cdef"
        km.keys = {}
        km.discover_from_env()

        try:
            import time
            for _ in range(5):
                km.get_key("openai")

            status = km.get_status()
            assert "openai" in status, f"openai not in status: {list(status.keys())}"
            rate = status["openai"]["rate_limit_rpm"]
            assert rate is not None, "Rate limit should not be None"
            assert rate >= 1, f"Expected rate limit >= 1, got {rate}"
        finally:
            if saved:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                del os.environ["OPENAI_API_KEY"]

    def test_12_configured_count(self, km):
        """Should correctly report the number of configured keys."""
        # First clean any existing keys
        for var in ["OPENAI_API_KEY", "GROQ_API_KEY"]:
            os.environ.pop(var, None)

        os.environ["OPENAI_API_KEY"] = "sk-tes...-key"

        try:
            km.keys = {}
            km.discover_from_env()
            count = km.get_configured_count()
            assert count >= 1, f"Expected >=1 configured keys, got {count}"
        finally:
            os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
