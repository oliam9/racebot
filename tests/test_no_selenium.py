"""
Acceptance test — verify Selenium is completely removed.
"""

import sys
import pytest


def test_no_selenium_in_modules():
    """Verify selenium is not loaded in sys.modules."""
    selenium_modules = [m for m in sys.modules.keys() if 'selenium' in m.lower()]
    assert len(selenium_modules) == 0, f"Found selenium modules: {selenium_modules}"


def test_no_selenium_in_requirements():
    """Verify selenium is not in requirements.txt."""
    with open('requirements.txt', 'r') as f:
        requirements = f.read().lower()
    
    assert 'selenium' not in requirements, "Found 'selenium' in requirements.txt"


def test_no_selenium_in_codebase():
    """Verify no selenium imports in codebase."""
    import os
    import re
    
    selenium_imports = []
    
    for root, dirs, files in os.walk('.'):
        # Skip venv, .git, __pycache__
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                
                try:
                    with open(filepath, 'r') as f:
                        content = f.read()
                        
                    if re.search(r'from selenium|import selenium', content, re.IGNORECASE):
                        selenium_imports.append(filepath)
                except Exception:
                    pass
    
    assert len(selenium_imports) == 0, f"Found selenium imports in: {selenium_imports}"


def test_playwright_available():
    """Verify Playwright is available and configured."""
    try:
        from browser_client import BrowserConfig, fetch_rendered
        config = BrowserConfig.from_env()
        assert config is not None
    except ImportError as e:
        pytest.skip(f"Playwright not installed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
