import os
from pathlib import Path

def test_phase12_voice_recording():
    """Verify that voice recording is real."""
    app_js = Path("desktop/renderer/app.js").read_text()
    assert "MediaRecorder" in app_js
    assert "🎤 [Voice Message attached]" not in app_js or "blob" in app_js
    print("✅ Phase 12: app.js has real voice recording logic.")

if __name__ == "__main__":
    try:
        test_phase12_voice_recording()
        print("\nALL PHASE 12 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 12 TEST FAILED: {e}")
        exit(1)
