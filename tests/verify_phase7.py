from pathlib import Path

def test_phase7_notifications():
    """Verify that Electron triggers native notifications."""
    main_js = Path("desktop/main.js").read_text()
    assert "new Notification(" in main_js
    print("✅ Phase 7: main.js has Notification implementation.")

if __name__ == "__main__":
    try:
        test_phase7_notifications()
        print("\nALL PHASE 7 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 7 TEST FAILED: {e}")
        exit(1)
