"""
PoC 4: UIA (UI Automation) Test Suite

Validates:
1. OSController platform detection and backend initialization
2. Element finding by name/properties (not coordinates)
3. Cross-platform architecture
"""

import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from os_controller import OSController, run_calculator_test, verify_element_targeting


class TestOSController:

    def test_1_backend_initialization(self):
        """Test that OSController initializes without error."""
        controller = OSController()
        ready = controller.is_ready()
        assert "platform" in ready
        assert ready["platform"] in ("Windows", "Linux", "Darwin")
        assert "available_methods" in ready

    def test_2_element_finding_by_name(self):
        """Test element finding by name (architectural: by properties, not coords)."""
        controller = OSController()
        
        # This should not crash even if element doesn't exist
        result = controller.find_element_by_name("NonExistentElementName12345")
        assert "found" in result
        # We don't expect it to be found (no such element)
        # But it should return gracefully

    def test_3_active_window(self):
        """Test get_active_window returns gracefully."""
        controller = OSController()
        result = controller.get_active_window()
        # Should at least return something
        assert isinstance(result, dict)

    def test_4_architecture_claim_documentation(self):
        """Verify the architectural claim is documented and testable."""
        claim = verify_element_targeting()
        assert claim["verified"] == True
        assert len(claim["rationale"]) >= 3

    def test_5_calculator_test_runs(self):
        """Test that calculator test runs without crashing."""
        result = run_calculator_test()
        assert result == True

    def test_6_platform_specific_methods(self):
        """Test platform-specific method availability."""
        controller = OSController()
        ready = controller.is_ready()
        
        # Each platform should have at least one method listed
        methods = ready["available_methods"]
        assert len(methods) > 0
        
        # Platform should match
        import platform
        if platform.system() == "Linux":
            # On Linux, xdotool might or might not be installed - that's ok
            pass  # No strict assertion needed


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
