import os
import json
import time
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

from . import config


class AccountManager:
    def __init__(self):
        config.MANAGER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        self.settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        if config.SETTINGS_FILE.exists():
            try:
                with open(config.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "active_profile_id": None,
            "profiles": {},
            "antigravity_exe": str(self.find_antigravity_exe() or ""),
            "auto_relaunch": True
        }

    def _save_settings(self) -> None:
        try:
            with open(config.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def find_antigravity_exe(self) -> Optional[Path]:
        saved = self.settings.get("antigravity_exe") if hasattr(self, "settings") else None
        if saved and Path(saved).exists():
            return Path(saved)

        for path in config.POSSIBLE_EXE_PATHS:
            if path.exists():
                return path

        try:
            cmd = 'powershell -NoProfile -Command "(Get-Process Antigravity -ErrorAction SilentlyContinue | Select-Object -First 1).Path"'
            res = subprocess.check_output(cmd, shell=True, text=True, timeout=3).strip()
            if res and Path(res).exists():
                return Path(res)
        except Exception:
            pass
        return None

    def is_antigravity_running(self) -> bool:
        try:
            cmd = 'powershell -NoProfile -Command "(Get-Process Antigravity -ErrorAction SilentlyContinue).Count"'
            out = subprocess.check_output(cmd, shell=True, text=True, timeout=3).strip()
            return int(out or 0) > 0
        except Exception:
            return False

    def close_antigravity(self, force: bool = False, timeout: int = 4) -> bool:
        if not self.is_antigravity_running():
            return True

        flag = "/F" if force else ""
        subprocess.run(f"taskkill {flag} /IM Antigravity.exe /T", shell=True, capture_output=True)

        start = time.time()
        while time.time() - start < timeout:
            if not self.is_antigravity_running():
                break
            time.sleep(0.4)

        if self.is_antigravity_running():
            subprocess.run("taskkill /F /IM Antigravity.exe /T", shell=True, capture_output=True)
            time.sleep(0.5)

        # Clean lingering Chromium lock files
        self._cleanup_locks()
        return not self.is_antigravity_running()

    def _cleanup_locks(self):
        """Cleans stale Chromium lockfiles to prevent crash on next startup."""
        lock_files = [
            config.ANTIGRAVITY_APP_DATA / "lockfile",
            config.ANTIGRAVITY_APP_DATA / "SingletonLock",
            config.ANTIGRAVITY_APP_DATA / "SingletonSocket",
            config.ANTIGRAVITY_APP_DATA / "SingletonCookie",
        ]
        for lf in lock_files:
            try:
                if lf.exists():
                    lf.unlink()
            except Exception:
                pass

    def launch_antigravity(self, isolated_profile_path: Optional[Path] = None) -> bool:
        exe = self.find_antigravity_exe()
        if not exe or not exe.exists():
            raise FileNotFoundError("Исполняемый файл Antigravity.exe не найден!")

        self._cleanup_locks()
        args = [str(exe)]
        if isolated_profile_path:
            isolated_profile_path.mkdir(parents=True, exist_ok=True)
            args.append(f'--user-data-dir="{isolated_profile_path}"')

        subprocess.Popen(" ".join(args), shell=True)
        return True

    def detect_current_account(self) -> Dict[str, Any]:
        app_storage = config.ANTIGRAVITY_APP_DATA / "app_storage.json"
        username = "Неизвестно"
        if app_storage.exists():
            try:
                with open(app_storage, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    username = data.get("jetski.onboarding.lastLoginUsername", "") or username
            except Exception:
                pass
        return {
            "email": username,
            "is_running": self.is_antigravity_running()
        }

    def list_profiles(self) -> List[Dict[str, Any]]:
        profiles = []
        active_id = self.settings.get("active_profile_id")
        for pid, data in self.settings.get("profiles", {}).items():
            profile_data = dict(data)
            profile_data["id"] = pid
            profile_data["is_active"] = (pid == active_id)
            profiles.append(profile_data)
        return sorted(profiles, key=lambda x: x.get("created_at", 0))

    def _copy_session_items(self, src_root: Path, dst_root: Path) -> None:
        dst_root.mkdir(parents=True, exist_ok=True)
        for item in config.SESSION_ITEMS:
            src = src_root / item
            dst = dst_root / item
            if not src.exists():
                continue
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

    def save_current_as_profile(self, profile_id: str, name: str, notes: str = "", quota_status: str = "ready") -> Dict[str, Any]:
        if self.is_antigravity_running():
            raise RuntimeError("Пожалуйста, закройте Antigravity перед сохранением профиля (для корректной фиксации куки)!")

        profile_dir = config.PROFILES_DIR / profile_id
        profile_dir.mkdir(parents=True, exist_ok=True)

        self._copy_session_items(config.ANTIGRAVITY_APP_DATA, profile_dir)

        saved_app_storage = profile_dir / "app_storage.json"
        email = "Неизвестный аккаунт"
        if saved_app_storage.exists():
            try:
                with open(saved_app_storage, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    email = data.get("jetski.onboarding.lastLoginUsername", "") or email
            except Exception:
                pass

        profile_info = {
            "name": name,
            "email": email,
            "notes": notes,
            "quota_status": quota_status,
            "created_at": time.time(),
            "last_used": time.time(),
        }

        self.settings.setdefault("profiles", {})[profile_id] = profile_info
        self.settings["active_profile_id"] = profile_id
        self._save_settings()
        return profile_info

    def switch_profile(self, profile_id: str, restart_app: bool = True) -> bool:
        """Atomic profile switch with safety rollback."""
        if profile_id not in self.settings.get("profiles", {}):
            raise ValueError(f"Профиль {profile_id} не найден!")

        # 1. Close Antigravity
        if self.is_antigravity_running():
            closed = self.close_antigravity()
            if not closed:
                raise RuntimeError("Не удалось остановить процесс Antigravity.exe!")

        # 2. Safety snapshot
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = config.BACKUPS_DIR / f"backup_{timestamp}"
        try:
            self._copy_session_items(config.ANTIGRAVITY_APP_DATA, backup_dir)
        except Exception:
            pass

        # Update current active profile with freshest cookies
        active_id = self.settings.get("active_profile_id")
        if active_id and (config.ANTIGRAVITY_APP_DATA / "Local State").exists():
            current_active_dir = config.PROFILES_DIR / active_id
            try:
                self._copy_session_items(config.ANTIGRAVITY_APP_DATA, current_active_dir)
            except Exception:
                pass

        # 3. Restore target profile
        target_dir = config.PROFILES_DIR / profile_id
        if not target_dir.exists():
            raise FileNotFoundError(f"Данные профиля {profile_id} не найдены на диске!")

        try:
            self._copy_session_items(target_dir, config.ANTIGRAVITY_APP_DATA)
            self._cleanup_locks()
        except Exception as e:
            # Rollback to backup
            if backup_dir.exists():
                self._copy_session_items(backup_dir, config.ANTIGRAVITY_APP_DATA)
            raise RuntimeError(f"Сбой при переключении профиля! Выполнен откат назад: {e}")

        # 4. Update state
        self.settings["active_profile_id"] = profile_id
        self.settings["profiles"][profile_id]["last_used"] = time.time()
        self._save_settings()

        # 5. Relaunch
        if restart_app:
            self.launch_antigravity()

        return True

    def delete_profile(self, profile_id: str) -> None:
        if profile_id in self.settings.get("profiles", {}):
            del self.settings["profiles"][profile_id]
            if self.settings.get("active_profile_id") == profile_id:
                self.settings["active_profile_id"] = None
            self._save_settings()

        target_dir = config.PROFILES_DIR / profile_id
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

    def update_profile_status(self, profile_id: str, quota_status: str, notes: Optional[str] = None) -> None:
        if profile_id in self.settings.get("profiles", {}):
            self.settings["profiles"][profile_id]["quota_status"] = quota_status
            if notes is not None:
                self.settings["profiles"][profile_id]["notes"] = notes
            self._save_settings()

    def prepare_clean_login_slot(self) -> None:
        if self.is_antigravity_running():
            closed = self.close_antigravity()
            if not closed:
                raise RuntimeError("Не удалось остановить Antigravity.exe!")

        active_id = self.settings.get("active_profile_id")
        if active_id:
            try:
                self._copy_session_items(config.ANTIGRAVITY_APP_DATA, config.PROFILES_DIR / active_id)
            except Exception:
                pass

        for item in config.SESSION_ITEMS:
            path = config.ANTIGRAVITY_APP_DATA / item
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    try:
                        path.unlink()
                    except Exception:
                        pass

        self._cleanup_locks()
        self.settings["active_profile_id"] = None
        self._save_settings()
        self.launch_antigravity()
