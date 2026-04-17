import os
import time
import subprocess
from typing import Dict, Any, Optional

try:
    import pyautogui
    pyautogui.FAILSAFE = False
except ImportError:
    pyautogui = None

from tools.base import audit_log

def _check_pyautogui():
    if pyautogui is None:
        raise ImportError("pyautogui is not installed. Please run \`pip install pyautogui pillow\`")

def gui_mouse_move(x: int, y: int, duration: float = 0.0) -> str:
    """Move the mouse cursor to a specific (x, y) coordinate."""
    _check_pyautogui()
    try:
        pyautogui.moveTo(x, y, duration=duration)
        audit_log("gui_mouse_move", {"x": x, "y": y}, "success", "Mouse moved")
        return f"Moved mouse to ({x}, {y})"
    except Exception as e:
        audit_log("gui_mouse_move", {"x": x, "y": y}, "error", str(e))
        return f"Error: {e}"

def gui_mouse_click(button: str = "left", clicks: int = 1) -> str:
    """Click the mouse."""
    _check_pyautogui()
    try:
        pyautogui.click(button=button, clicks=clicks)
        audit_log("gui_mouse_click", {"button": button, "clicks": clicks}, "success", "Mouse clicked")
        return f"Clicked {button} button {clicks} time(s)"
    except Exception as e:
        audit_log("gui_mouse_click", {"button": button, "clicks": clicks}, "error", str(e))
        return f"Error: {e}"

def gui_type_text(text: str, interval: float = 0.0) -> str:
    """Type a string of characters."""
    _check_pyautogui()
    try:
        pyautogui.write(text, interval=interval)
        audit_log("gui_type_text", {"text_len": len(text)}, "success", "Text typed")
        return f"Typed text of length {len(text)}"
    except Exception as e:
        audit_log("gui_type_text", {}, "error", str(e))
        return f"Error: {e}"

def gui_press_key(key: str) -> str:
    """Press a single key or a combination (e.g., 'enter', 'ctrl+c')."""
    _check_pyautogui()
    try:
        if '+' in key:
            keys = key.split('+')
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(key)
        audit_log("gui_press_key", {"key": key}, "success", "Key pressed")
        return f"Pressed key(s): {key}"
    except Exception as e:
        audit_log("gui_press_key", {"key": key}, "error", str(e))
        return f"Error: {e}"

def gui_screenshot(save_path: str = "screenshot.png") -> str:
    """Take a screenshot using scrot as a fallback if pyautogui fails on Linux."""
    try:
        # Try native pyautogui first
        pyautogui.screenshot(save_path)
        audit_log("gui_screenshot", {"path": save_path, "method": "pyautogui"}, "success", "Screenshot taken")
        return f"Screenshot saved to {save_path}"
    except Exception:
        try:
            # Fallback to scrot (external command)
            subprocess.run(["scrot", save_path], check=True)
            audit_log("gui_screenshot", {"path": save_path, "method": "scrot"}, "success", "Screenshot taken")
            return f"Screenshot saved to {save_path} (via scrot)"
        except Exception as e:
            audit_log("gui_screenshot", {"path": save_path}, "error", str(e))
            return f"Error taking screenshot: {e}"

def gui_get_screen_size() -> str:
    """Get the screen resolution. Uses xrandr as fallback."""
    _check_pyautogui()
    try:
        width, height = pyautogui.size()
        return f"Screen size is {width}x{height}"
    except Exception:
        try:
            output = subprocess.check_output("xrandr | grep '*' | awk '{print $1}'", shell=True, text=True)
            res = output.strip().split('\n')[0]
            return f"Screen size is {res} (via xrandr)"
        except Exception as e:
            return f"Error: {e}"
