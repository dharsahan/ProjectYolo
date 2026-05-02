from pathlib import Path

def test_phase3_renderer_reads_files():
    """Verify that app.js has logic to read file contents."""
    app_js = Path("desktop/renderer/app.js").read_text()
    assert "new FileReader()" in app_js or "readAsDataURL" in app_js
    print("✅ Phase 3: app.js reads file contents.")

def test_phase3_bridge_accepts_attachments():
    """Verify that api_bridge.py handle_chat and handle_chat_stream accept attachments."""
    bridge_py = Path("desktop/api_bridge.py").read_text()
    assert "attachments = data.get(\"attachments\"" in bridge_py
    assert "def handle_attachments(session, attachments):" in bridge_py
    assert "handle_attachments(session, attachments)" in bridge_py
    print("✅ Phase 3: api_bridge handles attachments.")

if __name__ == "__main__":
    try:
        test_phase3_renderer_reads_files()
        test_phase3_bridge_accepts_attachments()
        print("\nALL PHASE 3 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 3 TEST FAILED: {e}")
        exit(1)
