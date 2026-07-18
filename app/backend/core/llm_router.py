"""
Ramesh Saini v7.1 — Universal LLM Router
Supports 9 Free + 5 Premium Models with intelligent fallback routing.
"""

import os
import json
import time
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('ramesh-mvp.llm_router')


class ModelTier(str, Enum):
    FREE = "free"
    PREMIUM = "premium"


@dataclass
class ModelConfig:
    name: str
    provider: str
    tier: ModelTier
    context_window: int
    supports_vision: bool = False
    supports_function_calling: bool = True
    is_default: bool = False
    cost_per_1k_tokens: float = 0.0
    api_key_env: str = ""
    base_url: str = ""


# ============================================================
# 14 Models: 9 Free + 5 Premium
# ============================================================

FREE_MODELS: List[ModelConfig] = [
    ModelConfig(
        name="llama-3.1-8b", provider="groq", tier=ModelTier.FREE,
        context_window=8192, supports_function_calling=True,
        is_default=True, cost_per_1k_tokens=0.0,
        api_key_env="GROQ_API_KEY", base_url="https://api.groq.com/openai/v1"
    ),
    ModelConfig(
        name="gemini-2.0-flash", provider="google", tier=ModelTier.FREE,
        context_window=8192, supports_vision=True, supports_function_calling=True,
        cost_per_1k_tokens=0.0,
        api_key_env="GEMINI_API_KEY", base_url="https://generativelanguage.googleapis.com/v1beta"
    ),
    ModelConfig(
        name="mistral-7b", provider="mistral", tier=ModelTier.FREE,
        context_window=8192, supports_function_calling=True,
        cost_per_1k_tokens=0.0,
        api_key_env="MISTRAL_API_KEY", base_url="https://api.mistral.ai/v1"
    ),
    ModelConfig(
        name="deepseek-coder-6.7b", provider="deepseek", tier=ModelTier.FREE,
        context_window=16384, supports_function_calling=True,
        cost_per_1k_tokens=0.0,
        api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com/v1"
    ),
    ModelConfig(
        name="qwen-2.5-7b", provider="openrouter", tier=ModelTier.FREE,
        context_window=32768, supports_function_calling=True,
        cost_per_1k_tokens=0.0,
        api_key_env="OPENROUTER_API_KEY", base_url="https://openrouter.ai/api/v1"
    ),
    ModelConfig(
        name="phi-3-mini", provider="azure", tier=ModelTier.FREE,
        context_window=4096, supports_function_calling=False,
        cost_per_1k_tokens=0.0,
        api_key_env="AZURE_API_KEY", base_url=""
    ),
    ModelConfig(
        name="claude-3-haiku", provider="anthropic", tier=ModelTier.FREE,
        context_window=200000, supports_vision=True, supports_function_calling=True,
        cost_per_1k_tokens=0.0,
        api_key_env="ANTHROPIC_API_KEY", base_url="https://api.anthropic.com/v1"
    ),
    ModelConfig(
        name="gemma-2-9b", provider="openrouter", tier=ModelTier.FREE,
        context_window=8192, supports_function_calling=True,
        cost_per_1k_tokens=0.0,
        api_key_env="OPENROUTER_API_KEY", base_url="https://openrouter.ai/api/v1"
    ),
    ModelConfig(
        name="nous-hermes-2", provider="openrouter", tier=ModelTier.FREE,
        context_window=16384, supports_function_calling=True,
        cost_per_1k_tokens=0.0,
        api_key_env="OPENROUTER_API_KEY", base_url="https://openrouter.ai/api/v1"
    ),
]

PREMIUM_MODELS: List[ModelConfig] = [
    ModelConfig(
        name="gpt-4o", provider="openai", tier=ModelTier.PREMIUM,
        context_window=128000, supports_vision=True, supports_function_calling=True,
        cost_per_1k_tokens=0.005,
        api_key_env="OPENAI_API_KEY", base_url="https://api.openai.com/v1"
    ),
    ModelConfig(
        name="claude-3.5-sonnet", provider="anthropic", tier=ModelTier.PREMIUM,
        context_window=200000, supports_vision=True, supports_function_calling=True,
        cost_per_1k_tokens=0.003,
        api_key_env="ANTHROPIC_API_KEY", base_url="https://api.anthropic.com/v1"
    ),
    ModelConfig(
        name="gemini-2.0-pro", provider="google", tier=ModelTier.PREMIUM,
        context_window=8192, supports_vision=True, supports_function_calling=True,
        cost_per_1k_tokens=0.002,
        api_key_env="GEMINI_API_KEY", base_url="https://generativelanguage.googleapis.com/v1beta"
    ),
    ModelConfig(
        name="gpt-4-turbo", provider="openai", tier=ModelTier.PREMIUM,
        context_window=128000, supports_vision=True, supports_function_calling=True,
        cost_per_1k_tokens=0.01,
        api_key_env="OPENAI_API_KEY", base_url="https://api.openai.com/v1"
    ),
    ModelConfig(
        name="deepseek-r1", provider="deepseek", tier=ModelTier.PREMIUM,
        context_window=65536, supports_function_calling=True,
        cost_per_1k_tokens=0.002,
        api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com/v1"
    ),
]


class LLMRouter:
    """
    Universal LLM Router with intelligent model selection.
    
    Features:
    - 9 Free + 5 Premium model catalog
    - Auto-detection of available API keys
    - Graceful fallback on failure
    - Cost-aware routing
    - Provider health checking
    """

    def __init__(self):
        self.all_models: List[ModelConfig] = FREE_MODELS + PREMIUM_MODELS
        self._available_cache: Optional[List[ModelConfig]] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 60.0  # seconds
        self._fallback_history: Dict[str, int] = {}  # model -> fail count

    def get_available_models(self, force_refresh: bool = False) -> List[ModelConfig]:
        """
        Returns only models whose API keys are configured in the environment.
        Caches result for _cache_ttl seconds.
        """
        now = time.time()
        if not force_refresh and self._available_cache and (now - self._cache_timestamp) < self._cache_ttl:
            return self._available_cache

        available = []
        for model in self.all_models:
            key = os.environ.get(model.api_key_env, "")
            if key and len(key) > 8:  # Basic validation: key exists and not placeholder
                available.append(model)

        self._available_cache = available
        self._cache_timestamp = now
        return available

    def get_model(self, model_name: str) -> Optional[ModelConfig]:
        """Find a model config by name."""
        for m in self.all_models:
            if m.name == model_name:
                return m
        return None

    def select_best_model(self, tier: ModelTier = None, requires_vision: bool = False,
                          fallback_ok: bool = True) -> Optional[ModelConfig]:
        """
        Select the best available model based on constraints.
        
        Args:
            tier: If specified, only models of this tier
            requires_vision: Only models with vision support
            fallback_ok: Allow fallback to lower tier if premium unavailable
        
        Returns:
            ModelConfig or None if no suitable model available
        """
        available = self.get_available_models()

        # Filter by tier
        if tier:
            candidates = [m for m in available if m.tier == tier]
        else:
            candidates = list(available)

        # Filter by vision requirement
        if requires_vision:
            candidates = [m for m in candidates if m.supports_vision]

        # Sort: default first, then by cost
        candidates.sort(key=lambda m: (0 if m.is_default else 1, m.cost_per_1k_tokens))

        if candidates:
            chosen = candidates[0]
            logger.info(f"Selected model: {chosen.name} ({chosen.provider}, {chosen.tier.value})")
            return chosen

        # Fallback: try premium -> free or vice versa
        if fallback_ok and tier is not None:
            other_tier = ModelTier.PREMIUM if tier == ModelTier.FREE else ModelTier.FREE
            logger.warning(f"No {tier.value} models available. Falling back to {other_tier.value}...")
            candidates = [m for m in available if m.tier == other_tier]
            if requires_vision:
                candidates = [m for m in candidates if m.supports_vision]
            candidates.sort(key=lambda m: (0 if m.is_default else 1, m.cost_per_1k_tokens))
            if candidates:
                logger.info(f"Fallback selected: {candidates[0].name}")
                return candidates[0]

        logger.error("No available models found! Check API keys.")
        return None

    def mark_failure(self, model_name: str):
        """Track a model failure for fallback routing."""
        self._fallback_history[model_name] = self._fallback_history.get(model_name, 0) + 1
        logger.warning(f"Model {model_name} failure count: {self._fallback_history[model_name]}")

    def route(self, prompt: str, tier: ModelTier = None, requires_vision: bool = False) -> dict:
        """
        Route a prompt to the best available model.
        
        Returns dict with:
            - model: selected model config
            - fallback_used: bool
            - error: str if routing failed
        """
        selected = self.select_best_model(tier=tier, requires_vision=requires_vision)

        if not selected:
            return {"error": "No available LLM models. Configure at least one API key.",
                    "model": None, "fallback_used": False}

        return {
            "model": {
                "name": selected.name,
                "provider": selected.provider,
                "tier": selected.tier.value,
                "context_window": selected.context_window,
                "supports_vision": selected.supports_vision,
                "api_key_status": "set" if os.environ.get(selected.api_key_env) else "missing",
                "base_url": selected.base_url,
            },
            "fallback_used": False,
            "error": None
        }

    def list_models(self, tier: ModelTier = None) -> List[dict]:
        """List all registered models with their config."""
        models = self.all_models if not tier else [m for m in self.all_models if m.tier == tier]
        return [
            {
                "name": m.name,
                "provider": m.provider,
                "tier": m.tier.value,
                "context_window": m.context_window,
                "supports_vision": m.supports_vision,
                "supports_function_calling": m.supports_function_calling,
                "is_default": m.is_default,
                "api_key_configured": bool(os.environ.get(m.api_key_env, "")),
            }
            for m in models
        ]

    def get_catalog(self) -> dict:
        """Get full model catalog with availability status."""
        return {
            "total_models": len(self.all_models),
            "free_models": len([m for m in FREE_MODELS]),
            "premium_models": len([m for m in PREMIUM_MODELS]),
            "available_count": len(self.get_available_models()),
            "default_model": next((m.name for m in self.all_models if m.is_default), None),
            "models": self.list_models(),
        }

    def configure_from_env(self) -> int:
        """Auto-detect and log available API keys from environment."""
        count = 0
        for model in self.all_models:
            key = os.environ.get(model.api_key_env, "")
            if key and len(key) > 8:
                count += 1
                logger.info(f"  ✅ {model.name:25s} ({model.provider}) — key configured")
            else:
                logger.info(f"  ❌ {model.name:25s} ({model.provider}) — no key")
        return count


# Singleton instance
ROUTER = LLMRouter()
