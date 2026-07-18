"""
Tests for the Universal LLM Router — 9 Free + 5 Premium Models
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.llm_router import (
    LLMRouter, FREE_MODELS, PREMIUM_MODELS, ModelTier, ModelConfig
)


class TestLLMRouter:

    @pytest.fixture
    def router(self):
        return LLMRouter()

    def test_1_total_models_count(self, router):
        """Verify exactly 9 free + 5 premium = 14 total models."""
        total = len(FREE_MODELS) + len(PREMIUM_MODELS)
        assert total == 14, f"Expected 14 models, got {total}"
        assert len(FREE_MODELS) == 9, f"Expected 9 free models, got {len(FREE_MODELS)}"
        assert len(PREMIUM_MODELS) == 5, f"Expected 5 premium models, got {len(PREMIUM_MODELS)}"

    def test_2_model_catalog_structure(self, router):
        """Verify all models have required fields."""
        for model in FREE_MODELS + PREMIUM_MODELS:
            assert model.name, f"Model missing name"
            assert model.provider, f"Model {model.name} missing provider"
            assert model.api_key_env, f"Model {model.name} missing api_key_env"
            assert model.context_window > 0, f"Model {model.name} invalid context_window"
            assert isinstance(model.supports_vision, bool)
            assert isinstance(model.supports_function_calling, bool)

    def test_3_default_model_is_free(self, router):
        """Default model should be from the free tier."""
        defaults = [m for m in FREE_MODELS + PREMIUM_MODELS if m.is_default]
        assert len(defaults) >= 1, "No default model configured"
        assert defaults[0].tier == ModelTier.FREE, "Default model should be free"

    def test_4_get_model_by_name(self, router):
        """Test model lookup by name."""
        model = router.get_model("gpt-4o")
        assert model is not None
        assert model.provider == "openai"
        assert model.tier == ModelTier.PREMIUM

        model = router.get_model("nonexistent-model")
        assert model is None

    def test_5_list_models_count(self, router):
        """Test list_models returns correct counts."""
        all_models = router.list_models()
        assert len(all_models) == 14

        free = router.list_models(tier=ModelTier.FREE)
        assert len(free) == 9

        premium = router.list_models(tier=ModelTier.PREMIUM)
        assert len(premium) == 5

    def test_6_select_best_model_missing_keys(self, router):
        """Without API keys, selection should return None."""
        # Save and clear env keys
        saved = {}
        for model in FREE_MODELS + PREMIUM_MODELS:
            saved[model.api_key_env] = os.environ.get(model.api_key_env, "")
            if model.api_key_env in os.environ:
                del os.environ[model.api_key_env]

        try:
            router._available_cache = None
            result = router.select_best_model()
            assert result is None, "Should return None when no keys configured"
        finally:
            # Restore env
            for k, v in saved.items():
                if v:
                    os.environ[k] = v

    def test_7_select_best_model_with_mock_key(self, router):
        """With a mock key set, should return a model."""
        saved = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = "sk-tes...only"

        try:
            router._available_cache = None
            result = router.select_best_model()
            assert result is not None, "Should return a model when key is set"
            # With only OpenAI set, should return an OpenAI model or fallback
            assert result.provider in ("openai",), f"Expected openai provider, got {result.provider}/{result.name}"
            assert result.name is not None
        finally:
            if saved:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                del os.environ["OPENAI_API_KEY"]

    def test_8_select_premium_model(self, router):
        """Test selecting a premium-tier model."""
        saved = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = "sk-test-key-12345-for-testing-only"

        try:
            router._available_cache = None
            result = router.select_best_model(tier=ModelTier.PREMIUM)
            assert result is not None
            assert result.tier == ModelTier.PREMIUM
            assert result.provider == "openai", f"Expected openai, got {result.provider}"
        finally:
            if saved:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                del os.environ["OPENAI_API_KEY"]

    def test_9_vision_model_selection(self, router):
        """Test selecting a model with vision support."""
        saved = os.environ.get("ANTHROPIC_API_KEY", "")
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key-for-testing"

        try:
            router._available_cache = None
            result = router.select_best_model(requires_vision=True)
            assert result is not None
            assert result.supports_vision, f"Selected model {result.name} lacks vision support"
        finally:
            if saved:
                os.environ["ANTHROPIC_API_KEY"] = saved
            else:
                del os.environ["ANTHROPIC_API_KEY"]

    def test_10_fallback_on_failure(self, router):
        """Test marking failures triggers fallback."""
        saved = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = "sk-test-key-12345-for-testing-only"

        try:
            router._available_cache = None
            router.mark_failure("gpt-4o")
            router.mark_failure("gpt-4o")
            assert router._fallback_history.get("gpt-4o") == 2, "Failure count should be 2"
        finally:
            if saved:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                del os.environ["OPENAI_API_KEY"]

    def test_11_route_endpoint(self, router):
        """Test the route() API endpoint returns correct shape."""
        saved = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = "sk-test-key-12345-for-testing-only"

        try:
            router._available_cache = None
            result = router.route("Hello world")
            assert result["error"] is None
            assert result["model"] is not None
            assert result["model"]["name"] is not None
            assert result["model"]["provider"] is not None
            assert result["model"]["tier"] in ("free", "premium")
        finally:
            if saved:
                os.environ["OPENAI_API_KEY"] = saved
            else:
                del os.environ["OPENAI_API_KEY"]

    def test_12_get_catalog(self, router):
        """Test the catalog endpoint returns complete info."""
        catalog = router.get_catalog()
        assert catalog["total_models"] == 14
        assert catalog["free_models"] == 9
        assert catalog["premium_models"] == 5
        assert len(catalog["models"]) == 14

    def test_13_free_model_details(self, router):
        """Verify specific free model details."""
        llama = router.get_model("llama-3.1-8b")
        assert llama is not None
        assert llama.provider == "groq"
        assert llama.tier == ModelTier.FREE
        assert llama.is_default

        gemini = router.get_model("gemini-2.0-flash")
        assert gemini is not None
        assert gemini.provider == "google"
        assert gemini.supports_vision

    def test_14_premium_model_details(self, router):
        """Verify specific premium model details."""
        gpt4 = router.get_model("gpt-4o")
        assert gpt4 is not None
        assert gpt4.provider == "openai"
        assert gpt4.context_window == 128000
        assert gpt4.supports_vision

        claude = router.get_model("claude-3.5-sonnet")
        assert claude is not None
        assert claude.provider == "anthropic"
        assert claude.context_window == 200000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
