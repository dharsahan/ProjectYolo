from pathlib import Path

def test_phase4_auto_launch():
    """Verify that main.js spawns the python bridge."""
    main_js = Path("desktop/main.js").read_text()
    assert "child_process" in main_js
    assert "spawn" in main_js
    assert "api_bridge.py" in main_js
    print("✅ Phase 4: main.js spawns api_bridge.py.")

if __name__ == "__main__":
    try:
        test_phase4_auto_launch()
        print("\nALL PHASE 4 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 4 TEST FAILED: {e}")
        exit(1)
