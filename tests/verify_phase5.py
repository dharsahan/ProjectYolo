from pathlib import Path

def test_phase5_copy_button():
    """Verify that createMessageEl injects a copy button."""
    app_js = Path("desktop/renderer/app.js").read_text()
    assert "copy-btn" in app_js
    assert "navigator.clipboard.writeText" in app_js
    print("✅ Phase 5: app.js has copy button logic.")

if __name__ == "__main__":
    try:
        test_phase5_copy_button()
        print("\nALL PHASE 5 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 5 TEST FAILED: {e}")
        exit(1)
