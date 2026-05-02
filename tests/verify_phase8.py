from pathlib import Path

def test_phase8_global_shortcut():
    """Verify that main.js registers a global shortcut and imports globalShortcut."""
    main_js = Path("desktop/main.js").read_text()
    
    # Check for import
    assert "globalShortcut" in main_js, "globalShortcut not imported in main.js"
    
    # Check for registration
    assert "globalShortcut.register" in main_js, "globalShortcut.register not found in main.js"
    
    # Check for the shortcut key (allowing for cross-platform variations)
    assert "Shift+Y" in main_js, "Shortcut 'Shift+Y' not found in main.js"
    
    print("✅ Phase 8: main.js has globalShortcut implementation.")

if __name__ == "__main__":
    try:
        test_phase8_global_shortcut()
        print("\nALL PHASE 8 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 8 TEST FAILED: {e}")
        exit(1)
