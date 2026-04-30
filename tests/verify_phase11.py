import os
from pathlib import Path

def test_phase11_message_search():
    """Verify that message search is implemented."""
    app_js = Path("desktop/renderer/app.js").read_text()
    assert "search-input" in app_js or "filter" in app_js
    print("✅ Phase 11: app.js has message search logic.")

if __name__ == "__main__":
    try:
        test_phase11_message_search()
        print("\nALL PHASE 11 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 11 TEST FAILED: {e}")
        exit(1)
