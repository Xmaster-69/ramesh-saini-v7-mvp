"""
Ramesh Saini v7.1 — Ironclad MVP Backend
Security Guard Module — integrated from poc-security (AST PreCrime Analyzer)
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'poc-security', 'src'))
from precrime_analyzer import PreCrimeSecurityAnalyzer


class SecurityGuard:
    """
    The Ironclad Security Gate.
    Sits between LLM output and code execution.
    All AI-generated code MUST pass through this guard before execution.
    """

    def __init__(self, block_threshold: int = 6):
        self.analyzer = PreCrimeSecurityAnalyzer(block_threshold=block_threshold)
        self._block_count = 0
        self._pass_count = 0

    def inspect_code(self, code: str, source: str = "llm") -> dict:
        """
        Inspect AI-generated code for security threats.
        
        Returns:
            {
                'safe': bool,
                'blocked': bool,
                'threats': list,
                'score': int,
                'action': 'allow' | 'block' | 'warn'
            }
        """
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
            'analyzer': 'PreCrimeSecurityAnalyzer v7.1'
        }

    def get_stats(self) -> dict:
        return {
            'blocks': self._block_count,
            'passes': self._pass_count,
            'total': self._block_count + self._pass_count
        }


# Create a singleton guard instance
GUARD = SecurityGuard()


if __name__ == '__main__':
    # Test the guard
    safe_code = 'print("Hello, World!")'
    mal_code = 'import os\nos.system("rm -rf /")'
    
    result_safe = GUARD.inspect_code(safe_code)
    result_mal = GUARD.inspect_code(mal_code)
    
    print(f"Safe code: action={result_safe['action']}, blocked={result_safe['blocked']}")
    print(f"Malicious code: action={result_mal['action']}, blocked={result_mal['blocked']}")
    print(f"Stats: {GUARD.get_stats()}")
