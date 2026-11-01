import os
import sys
import time
import json
import hmac
import hashlib
import base64
import winreg
import ctypes
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Obfuscated Master Secret (assembled at runtime to resist simple string scraping)
_K_PARTS = [
    b"AGY_SEC_2026",
    b"@#9xK!mQ$",
    b"L1C3NS3_PR0T3CT10N",
    b"G00GL3_ANT1GRAV1TY"
]
MASTER_SECRET = hashlib.sha256(b"::".join(_K_PARTS)).digest()

PLANS = {
    "3d": {"name": "3 Дня", "days": 3, "price": "69 ₽"},
    "7d": {"name": "1 Неделя", "days": 7, "price": "119 ₽"},
    "30d": {"name": "1 Месяц", "days": 30, "price": "149 ₽"},
    "365d": {"name": "1 Год", "days": 365, "price": "399 ₽"},
}

# --- Anti-Tamper & Security Utilities ---

def is_debugger_present() -> bool:
    """Checks if a debugger is attached to the process (Anti-Crack / Anti-Debug)."""
    try:
        kernel32 = ctypes.windll.kernel32
        if kernel32.IsDebuggerPresent():
            return True
        is_remote = ctypes.c_bool(False)
        if hasattr(kernel32, "CheckRemoteDebuggerPresent"):
            kernel32.CheckRemoteDebuggerPresent(kernel32.GetCurrentProcess(), ctypes.byref(is_remote))
            if is_remote.value:
                return True
    except Exception:
        pass
    return False


def get_machine_hwid() -> str:
    """Calculates a unique, stable hardware identifier for this Windows machine."""
    components = []
    
    # 1. Windows MachineGuid from Registry
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            components.append(str(guid).strip())
    except Exception:
        pass

    # 2. System UUID / Motherboard
    try:
        import subprocess
        out = subprocess.check_output("wmic csproduct get uuid", shell=True, text=True, timeout=2)
        lines = [line.strip() for line in out.splitlines() if line.strip() and "UUID" not in line.upper()]
        if lines:
            components.append(lines[0])
    except Exception:
        pass

    # 3. Fallback: Machine identity
    components.append(os.environ.get("COMPUTERNAME", "PC"))
    components.append(os.environ.get("PROCESSOR_IDENTIFIER", "CPU"))

    raw = "||".join(components).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest().upper()
    return f"AGY-{digest[:4]}-{digest[4:8]}-{digest[8:12]}"


class LicenseManager:
    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
            storage_dir = user_profile / ".antigravity_account_manager"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.license_file = self.storage_dir / "license.dat"
        self.security_file = self.storage_dir / ".sec_state"
        self.hwid = get_machine_hwid()

    # --- Anti-Bruteforce Rate Limiter ---
    def _check_rate_limit(self) -> Tuple[bool, str]:
        now = time.time()
        state = {"failed_attempts": 0, "locked_until": 0}
        if self.security_file.exists():
            try:
                with open(self.security_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception:
                pass

        if now < state.get("locked_until", 0):
            remain = int(state["locked_until"] - now)
            return False, f"Слишком много неверных попыток! Блокировка на {remain} сек."
        return True, ""

    def _record_failed_attempt(self):
        now = time.time()
        state = {"failed_attempts": 0, "locked_until": 0}
        if self.security_file.exists():
            try:
                with open(self.security_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception:
                pass
        
        attempts = state.get("failed_attempts", 0) + 1
        state["failed_attempts"] = attempts
        if attempts >= 5:
            # Lock for 60 seconds after 5 failed attempts
            state["locked_until"] = now + 60
            state["failed_attempts"] = 0
        try:
            with open(self.security_file, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except Exception:
            pass

    def _reset_failed_attempts(self):
        try:
            if self.security_file.exists():
                self.security_file.unlink()
        except Exception:
            pass

    # --- Key Operations ---

    @staticmethod
    def generate_key(plan_code: str, hwid: Optional[str] = None, custom_days: Optional[int] = None) -> str:
        """Generates a signed license key."""
        plan_code = plan_code.lower()
        if plan_code in PLANS:
            days = PLANS[plan_code]["days"]
        else:
            days = custom_days or 30

        target_hwid = (hwid.strip().upper() if hwid else "ANY")
        nonce = os.urandom(4).hex().upper()
        payload = f"{plan_code}:{days}:{target_hwid}:{nonce}"
        sig = hmac.new(MASTER_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:12].upper()
        
        raw_token = f"{payload}:{sig}"
        encoded = base64.b32encode(raw_token.encode("utf-8")).decode("utf-8").rstrip("=")
        chunks = [encoded[i:i+5] for i in range(0, len(encoded), 5)]
        return "AGY-" + "-".join(chunks)

    @staticmethod
    def decode_and_verify_key(key_str: str, current_hwid: str) -> Tuple[bool, str, Dict[str, Any]]:
        cleaned = key_str.strip().upper()
        if cleaned.startswith("AGY-"):
            cleaned = cleaned[4:]
        cleaned = cleaned.replace("-", "")

        missing_padding = len(cleaned) % 8
        if missing_padding:
            cleaned += "=" * (8 - missing_padding)

        try:
            raw = base64.b32decode(cleaned.encode("utf-8")).decode("utf-8")
            parts = raw.split(":")
            if len(parts) != 5:
                return False, "Неверный формат ключа!", {}
            plan_code, days_str, target_hwid, nonce, sig = parts
            days = int(days_str)
            
            payload = f"{plan_code}:{days}:{target_hwid}:{nonce}"
            expected_sig = hmac.new(MASTER_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:12].upper()
            if not hmac.compare_digest(sig, expected_sig):
                return False, "Поддельный или повреждённый ключ активации!", {}

            if target_hwid != "ANY" and target_hwid != current_hwid:
                return False, f"Этот ключ привязан к другому компьютеру ({target_hwid})!", {}

            return True, "Ключ действителен", {
                "plan_code": plan_code,
                "days": days,
                "target_hwid": target_hwid,
                "nonce": nonce
            }
        except Exception:
            return False, "Не удалось распознать лицензионный ключ!", {}

    def activate_key(self, key_str: str) -> Tuple[bool, str]:
        # Anti-debug verification
        if is_debugger_present():
            return False, "Обнаружена среда отладки. Доступ заблокирован в целях безопасности."

        # Anti-bruteforce check
        allowed, limit_msg = self._check_rate_limit()
        if not allowed:
            return False, limit_msg

        valid, msg, info = self.decode_and_verify_key(key_str, self.hwid)
        if not valid:
            self._record_failed_attempt()
            return False, msg

        self._reset_failed_attempts()
        days = info["days"]
        plan_code = info["plan_code"]

        now = time.time()
        status = self.check_license()
        if status["is_active"] and status["expires_at"] > now:
            expires_at = status["expires_at"] + (days * 86400)
        else:
            expires_at = now + (days * 86400)

        license_data = {
            "key": key_str.strip(),
            "plan_code": plan_code,
            "hwid": self.hwid,
            "activated_at": now,
            "expires_at": expires_at,
            "last_check": now
        }

        sealed = self._seal_license(license_data)
        try:
            with open(self.license_file, "w", encoding="utf-8") as f:
                f.write(sealed)
            return True, f"Успешно активировано! Доступ открыт на {days} дн. (до {time.strftime('%d.%m.%Y %H:%M', time.localtime(expires_at))})"
        except Exception as e:
            return False, f"Ошибка записи файла лицензии: {e}"

    def check_license(self) -> Dict[str, Any]:
        if is_debugger_present():
            return {
                "is_active": False,
                "reason": "debugger_detected",
                "message": "Обнаружена среда отладки!",
                "hwid": self.hwid,
                "expires_at": 0,
                "days_left": 0
            }

        if not self.license_file.exists():
            return {
                "is_active": False,
                "reason": "not_activated",
                "message": "Лицензия не активирована",
                "hwid": self.hwid,
                "expires_at": 0,
                "days_left": 0
            }

        try:
            with open(self.license_file, "r", encoding="utf-8") as f:
                sealed = f.read().strip()
            data = self._unseal_license(sealed)
            if not data:
                return {
                    "is_active": False,
                    "reason": "tampered",
                    "message": "Файл лицензии повреждён или подделан",
                    "hwid": self.hwid,
                    "expires_at": 0,
                    "days_left": 0
                }

            if data.get("hwid") != self.hwid:
                return {
                    "is_active": False,
                    "reason": "hwid_mismatch",
                    "message": "Лицензия скопирована с другого компьютера",
                    "hwid": self.hwid,
                    "expires_at": 0,
                    "days_left": 0
                }

            now = time.time()
            last_check = data.get("last_check", 0)
            if now < (last_check - 3600):
                return {
                    "is_active": False,
                    "reason": "clock_tampered",
                    "message": "Обнаружен перевод системного времени назад!",
                    "hwid": self.hwid,
                    "expires_at": data.get("expires_at", 0),
                    "days_left": 0
                }

            expires_at = data.get("expires_at", 0)
            if now > expires_at:
                return {
                    "is_active": False,
                    "reason": "expired",
                    "message": "Срок действия лицензии истёк",
                    "hwid": self.hwid,
                    "expires_at": expires_at,
                    "days_left": 0
                }

            data["last_check"] = now
            try:
                with open(self.license_file, "w", encoding="utf-8") as f:
                    f.write(self._seal_license(data))
            except Exception:
                pass

            remaining_sec = max(0, expires_at - now)
            days_left = int(remaining_sec // 86400)
            hours_left = int((remaining_sec % 86400) // 3600)

            return {
                "is_active": True,
                "reason": "valid",
                "message": f"Осталось {days_left} дн. {hours_left} ч.",
                "hwid": self.hwid,
                "plan_code": data.get("plan_code", "30d"),
                "expires_at": expires_at,
                "days_left": days_left,
                "hours_left": hours_left,
                "expires_str": time.strftime("%d.%m.%Y %H:%M", time.localtime(expires_at))
            }
        except Exception:
            return {
                "is_active": False,
                "reason": "error",
                "message": "Ошибка проверки лицензии",
                "hwid": self.hwid,
                "expires_at": 0,
                "days_left": 0
            }

    def _seal_license(self, data: Dict[str, Any]) -> str:
        raw_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        sig = hmac.new(MASTER_SECRET + self.hwid.encode("utf-8"), raw_json.encode("utf-8"), hashlib.sha256).hexdigest()
        packet = f"{raw_json}||{sig}"
        return base64.b64encode(packet.encode("utf-8")).decode("utf-8")

    def _unseal_license(self, sealed_str: str) -> Optional[Dict[str, Any]]:
        try:
            packet = base64.b64decode(sealed_str.encode("utf-8")).decode("utf-8")
            raw_json, sig = packet.split("||", 1)
            expected_sig = hmac.new(MASTER_SECRET + self.hwid.encode("utf-8"), raw_json.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return None
            return json.loads(raw_json)
        except Exception:
            return None
