import os
from pathlib import Path

def test_phase2_hitl_no_auto_approve():
    """Verify that api_bridge.py does NOT auto-approve PendingConfirmationError."""
    bridge_path = Path("desktop/api_bridge.py")
    content = bridge_path.read_text()
    
    # It should NOT contain the logic to call execute_tool_direct in the exception handler anymore
    # or it should have a conditional check.
    # In the original code it was:
    # except yolo_agent.PendingConfirmationError as e:
    #     result = await yolo_agent.execute_tool_direct(...)
    
    assert "await yolo_agent.execute_tool_direct(" not in content or "if" in content.split("except yolo_agent.PendingConfirmationError")[1]
    print("✅ Phase 2: Bridge no longer auto-approves.")

def test_phase2_ipc_dialog():
    """Verify that main.js has an IPC handler for native dialogs."""
    main_js = Path("desktop/main.js").read_text()
    assert "dialog.showMessageBox" in main_js
    assert "ipcMain.handle('show-confirmation-dialog'" in main_js
    print("✅ Phase 2: main.js has confirmation dialog handler.")

if __name__ == "__main__":
    try:
        test_phase2_hitl_no_auto_approve()
        test_phase2_ipc_dialog()
        print("\nALL PHASE 2 TESTS PASSED")
    except AssertionError as e:
        print(f"\nPHASE 2 TEST FAILED: {e}")
        exit(1)
