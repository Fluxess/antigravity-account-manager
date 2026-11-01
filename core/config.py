import os
from pathlib import Path

# Base paths
USER_PROFILE = Path(os.environ.get("USERPROFILE", str(Path.home())))
APPDATA_ROAMING = Path(os.environ.get("APPDATA", str(USER_PROFILE / "AppData" / "Roaming")))
APPDATA_LOCAL = Path(os.environ.get("LOCALAPPDATA", str(USER_PROFILE / "AppData" / "Local")))

# Antigravity paths
ANTIGRAVITY_APP_DATA = APPDATA_ROAMING / "Antigravity"
ANTIGRAVITY_GEMINI_DATA = USER_PROFILE / ".gemini" / "antigravity"

# Possible paths for Antigravity executable
POSSIBLE_EXE_PATHS = [
    APPDATA_LOCAL / "Programs" / "antigravity" / "Antigravity.exe",
    Path("C:/Program Files/Antigravity/Antigravity.exe"),
    Path("C:/Program Files (x86)/Antigravity/Antigravity.exe"),
]

# Manager data directory
MANAGER_DATA_DIR = USER_PROFILE / ".antigravity_account_manager"
PROFILES_DIR = MANAGER_DATA_DIR / "profiles"
BACKUPS_DIR = MANAGER_DATA_DIR / "backups"
SETTINGS_FILE = MANAGER_DATA_DIR / "settings.json"

# Critical session files & folders to sync
SESSION_ITEMS = [
    "Local Storage",
    "Session Storage",
    "Network",
    "Local State",
    "app_storage.json",
    "Preferences",
]
