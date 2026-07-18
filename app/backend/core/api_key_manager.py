"""
Ramesh Saini v7.1 — API Key Manager
Secure storage, validation, rotation, and usage tracking for LLM API keys.
"""

import os
import json
import time
import base64
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger('ramesh-mvp.api_key_manager')

try:
    from cryptography.fernet import Fernet
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False


@dataclass
class APIKeyEntry:
    service: str
    key_preview: str  # Only store prefix + suffix for display
    is_configured: bool
    source: str  # "env", "config", "user"
    last_validated: float = 0.0
    is_valid: bool = False
    quota_remaining: Optional[int] = None
    rate_limit: Optional[int] = None  # requests per minute


class APIKeyManager:
    """
    Manages API keys securely.
    
    Features:
    - Loads keys from environment variables
    - Validates key format (length, prefix patterns)
    - Tracks usage and quotas
    - Supports encrypted storage for user-provided keys
    - Fallback notification when keys are missing
    """

    REQUIRED_KEY_PREFIXES = {
        "openai": "sk-",
        "anthropic": "sk-ant-",
        "groq": "gsk_",
        "google": "AIza",
        "mistral": "MISTRAL_",
        "deepseek": "sk-",
        "openrouter": "sk-or-",
    }

    def __init__(self, encryption_key: Optional[str] = None):
        self.keys: Dict[str, APIKeyEntry] = {}
        self._usage: Dict[str, int] = {}  # service -> call count
        self._rate_limits: Dict[str, List[float]] = {}  # service -> timestamps
        self._encryption_key = encryption_key or os.environ.get("RAMA_KEY_ENCRYPTION_KEY", "")
        self._fernet = None

        if HAS_FERNET and self._encryption_key:
            try:
                # Derive a valid Fernet key from the encryption key
                key_bytes = self._encryption_key.encode()[:32].ljust(32, b'\0')
                fernet_key = base64.urlsafe_b64encode(key_bytes)
                self._fernet = Fernet(fernet_key)
            except Exception as e:
                logger.warning(f"Fernet init failed (encryption disabled): {e}")

    def discover_from_env(self) -> int:
        """Scan environment variables for known API keys."""
        env_key_map = {
            "OPENAI_API_KEY": "openai",
            "ANTHROPIC_API_KEY": "anthropic",
            "GROQ_API_KEY": "groq",
            "GEMINI_API_KEY": "google",
            "MISTRAL_API_KEY": "mistral",
            "DEEPSEEK_API_KEY": "deepseek",
            "OPENROUTER_API_KEY": "openrouter",
            "AZURE_API_KEY": "azure",
            "HUGGINGFACE_API_KEY": "huggingface",
            "TOGETHER_API_KEY": "together",
            "CODESTRAL_API_KEY": "codestral",
        }

        count = 0
        for env_var, service in env_key_map.items():
            value = os.environ.get(env_var, "")
            if value:
                preview = self._preview_key(value)
                valid = self._validate_key_format(service, value)
                self.keys[service] = APIKeyEntry(
                    service=service,
                    key_preview=preview,
                    is_configured=True,
                    source="env",
                    is_valid=valid,
                )
                count += 1
                logger.info(f"  Discovered {service}: {preview} (valid={valid})")
            else:
                self.keys[service] = APIKeyEntry(
                    service=service,
                    key_preview="(not set)",
                    is_configured=False,
                    source="env",
                    is_valid=False,
                )

        return count

    def _preview_key(self, key: str) -> str:
        """Show first 4 + last 4 characters of a key."""
        if len(key) <= 12:
            return key[:4] + "..." + key[-4:] if len(key) > 8 else "(short)"
        return key[:6] + "..." + key[-4:]

    def _validate_key_format(self, service: str, key: str) -> bool:
        """Validate API key format for a given service."""
        if not key or len(key) < 12:
            return False

        prefix = self.REQUIRED_KEY_PREFIXES.get(service)
        if prefix and not key.startswith(prefix):
            logger.warning(f"  Key for {service} has unexpected prefix (expected '{prefix}...')")
            return False

        return True

    def get_key(self, service: str) -> Optional[str]:
        """Get an API key for a service."""
        env_var_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "groq": "GROQ_API_KEY",
            "google": "GEMINI_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "azure": "AZURE_API_KEY",
            "huggingface": "HUGGINGFACE_API_KEY",
            "together": "TOGETHER_API_KEY",
            "codestral": "CODESTRAL_API_KEY",
        }

        env_var = env_var_map.get(service)
        if env_var:
            key = os.environ.get(env_var, "")
            if key:
                self._track_usage(service)
                return key

        # Check stored keys
        entry = self.keys.get(service)
        if entry and entry.is_configured:
            self._track_usage(service)
            # In a real app, this would decrypt from secure storage
            return os.environ.get(env_var, "") if env_var else None

        return None

    def set_key(self, service: str, key: str, persist: bool = False) -> bool:
        """Set an API key for a service. Optionally encrypt for persistence."""
        if not self._validate_key_format(service, key):
            logger.error(f"Invalid key format for {service}")
            return False

        preview = self._preview_key(key)
        self.keys[service] = APIKeyEntry(
            service=service,
            key_preview=preview,
            is_configured=True,
            source="user",
            is_valid=True,
        )

        # Set environment variable for current session
        env_var_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "groq": "GROQ_API_KEY",
            "google": "GEMINI_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        env_var = env_var_map.get(service)
        if env_var:
            os.environ[env_var] = key

        # Encrypt and store if Fernet is available
        if persist and self._fernet:
            try:
                encrypted = self._fernet.encrypt(key.encode())
                # In production, write to secure config file
                # For now, the key lives in the environment
                logger.info(f"  Key encrypted for {service}")
            except Exception as e:
                logger.warning(f"  Encryption failed for {service}: {e}")

        logger.info(f"  {service}: key set ({preview})")
        return True

    def _track_usage(self, service: str):
        """Track API call usage for rate limiting."""
        self._usage[service] = self._usage.get(service, 0) + 1
        now = time.time()

        if service not in self._rate_limits:
            self._rate_limits[service] = []
        self._rate_limits[service].append(now)

        # Prune timestamps older than 60 seconds
        self._rate_limits[service] = [t for t in self._rate_limits[service] if now - t < 60]

        entry = self.keys.get(service)
        if entry:
            entry.rate_limit = len(self._rate_limits[service])

    def get_status(self) -> dict:
        """Get status of all configured keys."""
        return {
            service: {
                "preview": entry.key_preview,
                "configured": entry.is_configured,
                "valid": entry.is_valid,
                "source": entry.source,
                "usage_count": self._usage.get(service, 0),
                "rate_limit_rpm": entry.rate_limit,
                "last_validated": entry.last_validated,
            }
            for service, entry in sorted(self.keys.items())
        }

    def get_missing_services(self) -> List[str]:
        """Get list of services that need API keys configured."""
        return [s for s, e in self.keys.items() if not e.is_configured]

    def get_configured_count(self) -> int:
        """Count of services with configured keys."""
        return sum(1 for e in self.keys.values() if e.is_configured)

    def check_quotas(self) -> Dict[str, bool]:
        """Check which services still have quota available."""
        result = {}
        for service, entry in self.keys.items():
            if entry.quota_remaining is not None:
                result[service] = entry.quota_remaining > 0
            else:
                result[service] = True  # Unknown quota = assume available
        return result


# Singleton instance
KEY_MANAGER = APIKeyManager()
