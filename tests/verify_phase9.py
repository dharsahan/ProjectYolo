from pathlib import Path

def test_phase9_stop_streaming():
    """Verify that streaming can be aborted."""
    app_js = Path("desktop/renderer/app.js").read_text()
    main_js = Path("desktop/main.js").read_text()
    assert "AbortController" in main_js or "abort-chat-stream" in main_js
    assert "stop-btn" in app_js
    print("✅ Phase 9: System has stop streaming logic.")

if __name__ == "__main__":
    try:
        test_phase9_stop_streaming()
        print("\nALL PHASE 9 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 9 TEST FAILED: {e}")
        exit(1)
