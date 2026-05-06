import json
import os
from pathlib import Path

YOLO_HOME = Path(os.getenv("YOLO_HOME", str(Path.home() / ".yolo"))).expanduser().resolve()
SETTINGS_FILE = YOLO_HOME / "settings.json"

def load_settings():
    """Loads settings.json into os.environ."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                settings = json.load(f)
            for k, v in settings.items():
                if isinstance(v, str):
                    os.environ[k] = v
                else:
                    os.environ[k] = json.dumps(v)
        except Exception as e:
            print(f"Error loading settings from {SETTINGS_FILE}: {e}")

def update_setting(key: str, value: str):
    """Updates a single setting in settings.json and os.environ."""
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                settings = json.load(f)
        except Exception:
            pass
            
    settings[key] = value
    
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)
        
    os.environ[key] = str(value)
