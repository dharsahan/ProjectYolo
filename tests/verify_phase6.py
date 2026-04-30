import os
from pathlib import Path

def test_phase6_system_tray():
    """Verify that main.js uses Tray and has the required menu items."""
    main_js = Path("desktop/main.js").read_text()
    
    # Check for basic Tray implementation
    assert "new Tray(" in main_js
    assert "Menu.buildFromTemplate" in main_js
    
    # Check for required menu items
    assert "Show/Hide Window" in main_js
    assert "Toggle YOLO Mode" in main_js
    assert "Exit" in main_js
    
    # Check for IPC/fetch used in Toggle YOLO Mode
    assert "fetch" in main_js
    assert "/session" in main_js
    assert "/command" in main_js
    
    print("✅ Phase 6: main.js has Tray implementation with all required menu items.")

if __name__ == "__main__":
    try:
        test_phase6_system_tray()
        print("\nALL PHASE 6 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 6 TEST FAILED: {e}")
        exit(1)
