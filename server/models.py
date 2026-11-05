import sqlite3
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

DB_PATH = Path(__file__).parent / "licenses.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT UNIQUE NOT NULL,
        plan_code TEXT NOT NULL,
        days INTEGER NOT NULL,
        price TEXT NOT NULL,
        hwid TEXT,
        is_active INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        activated_at REAL,
        expires_at REAL,
        last_check REAL,
        buyer_note TEXT,
        created_at REAL NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_id TEXT UNIQUE NOT NULL,
        amount TEXT NOT NULL,
        plan_code TEXT NOT NULL,
        hwid TEXT,
        status TEXT NOT NULL,
        created_at REAL NOT NULL
    )
    """)
    conn.commit()
    conn.close()


class Database:
    @staticmethod
    def create_license(key: str, plan_code: str, days: int, price: str, buyer_note: str = "", hwid: Optional[str] = None) -> Dict[str, Any]:
        conn = get_db()
        cursor = conn.cursor()
        now = time.time()
        cursor.execute("""
        INSERT INTO licenses (license_key, plan_code, days, price, hwid, buyer_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (key, plan_code, days, price, hwid or None, buyer_note, now))
        conn.commit()
        conn.close()
        return {
            "key": key,
            "plan_code": plan_code,
            "days": days,
            "price": price,
            "hwid": hwid,
            "buyer_note": buyer_note,
            "created_at": now
        }

    @staticmethod
    def get_license(key: str) -> Optional[Dict[str, Any]]:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM licenses WHERE license_key = ?", (key.strip().upper(),))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_licenses() -> List[Dict[str, Any]]:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM licenses ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def activate_license(key: str, hwid: str) -> Dict[str, Any]:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM licenses WHERE license_key = ?", (key.strip().upper(),))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "Ключ не найден в базе данных!"}

        lic = dict(row)
        if lic["is_blocked"]:
            conn.close()
            return {"success": False, "message": "Этот ключ заблокирован администратором!"}

        # Check HWID binding
        target_hwid = lic["hwid"]
        if target_hwid and target_hwid != "ANY" and target_hwid != hwid:
            conn.close()
            return {"success": False, "message": f"Ключ уже привязан к другому оборудованию ({target_hwid})!"}

        now = time.time()
        days = lic["days"]
        
        # If already active, check if adding days
        if lic["is_active"] and lic["expires_at"] and lic["expires_at"] > now:
            expires_at = lic["expires_at"] + (days * 86400)
        else:
            expires_at = now + (days * 86400)

        cursor.execute("""
        UPDATE licenses 
        SET is_active = 1, hwid = ?, activated_at = COALESCE(activated_at, ?), expires_at = ?, last_check = ?
        WHERE license_key = ?
        """, (hwid, now, expires_at, now, key.strip().upper()))
        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Успешно активировано! Доступ до {time.strftime('%d.%m.%Y %H:%M', time.localtime(expires_at))}",
            "expires_at": expires_at,
            "days_left": int((expires_at - now) // 86400),
            "plan_code": lic["plan_code"]
        }

    @staticmethod
    def check_license(key: str, hwid: str) -> Dict[str, Any]:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM licenses WHERE license_key = ?", (key.strip().upper(),))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"is_valid": False, "message": "Ключ не найден!"}

        lic = dict(row)
        if lic["is_blocked"]:
            conn.close()
            return {"is_valid": False, "message": "Ключ заблокирован!"}

        if not lic["is_active"]:
            conn.close()
            return {"is_valid": False, "message": "Ключ ещё не был активирован!"}

        if lic["hwid"] and lic["hwid"] != hwid:
            conn.close()
            return {"is_valid": False, "message": "Несовпадение HWID!"}

        now = time.time()
        expires_at = lic["expires_at"] or 0
        if now > expires_at:
            conn.close()
            return {"is_valid": False, "message": "Срок действия лицензии истёк!"}

        # Update last_check
        cursor.execute("UPDATE licenses SET last_check = ? WHERE license_key = ?", (now, key.strip().upper()))
        conn.commit()
        conn.close()

        remaining_sec = max(0, expires_at - now)
        days_left = int(remaining_sec // 86400)
        hours_left = int((remaining_sec % 86400) // 3600)

        return {
            "is_valid": True,
            "message": f"Активно: {days_left} дн. {hours_left} ч.",
            "expires_at": expires_at,
            "days_left": days_left,
            "hours_left": hours_left,
            "plan_code": lic["plan_code"]
        }

    @staticmethod
    def toggle_block(key: str) -> bool:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT is_blocked FROM licenses WHERE license_key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        new_val = 0 if row["is_blocked"] else 1
        cursor.execute("UPDATE licenses SET is_blocked = ? WHERE license_key = ?", (new_val, key))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def extend_license(key: str, extra_days: int) -> bool:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT expires_at FROM licenses WHERE license_key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        now = time.time()
        current_exp = row["expires_at"] or now
        new_exp = max(now, current_exp) + (extra_days * 86400)
        cursor.execute("UPDATE licenses SET expires_at = ?, is_active = 1 WHERE license_key = ?", (new_exp, key))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def delete_license(key: str) -> bool:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM licenses WHERE license_key = ?", (key,))
        conn.commit()
        conn.close()
        return True


init_db()
