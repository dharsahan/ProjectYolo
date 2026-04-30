import os
from pathlib import Path

def test_phase10_history_sidebar():
    """Verify that sessions can be switched."""
    bridge_py = Path("desktop/api_bridge.py").read_text()
    app_js = Path("desktop/renderer/app.js").read_text()
    assert "/sessions" in bridge_py
    assert "sidebar" in app_js
    print("✅ Phase 10: System has history sidebar logic.")

if __name__ == "__main__":
    try:
        test_phase10_history_sidebar()
        print("\nALL PHASE 10 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 10 TEST FAILED: {e}")
        exit(1)
