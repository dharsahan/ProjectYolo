# Global Keyboard Shortcut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a global keyboard shortcut (`Cmd+Shift+Y` or `Ctrl+Shift+Y`) to toggle the visibility and focus of the Electron app window.

**Architecture:** Modify the Electron main process (`desktop/main.js`) to register the shortcut using the `globalShortcut` module. The handler will check if the window is currently visible/focused and toggle its state accordingly.

**Tech Stack:** Electron.

---

### Task 1: Register Global Shortcut in `desktop/main.js`

**Files:**
- Modify: `desktop/main.js`
- Modify: `tests/verify_phase8.py`

- [ ] **Step 1: Write the failing test (Updating existing test)**
Modify `tests/verify_phase8.py` to check for specific implementations.

```python
import os
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/verify_phase8.py`
Expected: FAIL

- [ ] **Step 3: Write implementation in `desktop/main.js`**

1. Update imports:
```javascript
const { app, BrowserWindow, ipcMain, dialog, Tray, Menu, Notification, globalShortcut } = require('electron');
```

2. Add `toggleWindow` function:
```javascript
function toggleWindow() {
  if (!mainWindow) {
    createWindow();
  } else if (mainWindow.isVisible() && mainWindow.isFocused()) {
    mainWindow.hide();
  } else {
    mainWindow.show();
    mainWindow.focus();
  }
}
```

3. Update tray menu:
```javascript
    {
      label: 'Show/Hide Window',
      click: () => toggleWindow()
    },
```

4. Register shortcut in `app.whenReady()`:
```javascript
  // Register global shortcut
  const shortcut = process.platform === 'darwin' ? 'Command+Shift+Y' : 'Control+Shift+Y';
  const ret = globalShortcut.register(shortcut, () => {
    console.log(`[main] Global shortcut ${shortcut} pressed`);
    toggleWindow();
  });

  if (!ret) {
    console.error('[main] Registration failed for shortcut:', shortcut);
  }

  app.on('will-quit', () => {
    // Unregister all shortcuts
    globalShortcut.unregisterAll();
  });
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/verify_phase8.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add desktop/main.js tests/verify_phase8.py
git commit -m "feat(electron): implement global keyboard shortcut to toggle window"
```
