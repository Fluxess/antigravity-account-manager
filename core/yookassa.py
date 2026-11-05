import os
import json
import uuid
import base64
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Secret config is stored LOCALLY and never committed to git
CONFIG_FILE = Path(__file__).parent / "yookassa_config.json"

API_URL = "https://api.yookassa.ru/v3/payments"

PLAN_PRICES = {
    "3d": {"amount": "69.00", "description": "Antigravity Manager — Доступ на 3 Дня", "days": 3, "label": "3 Дня (69 ₽)"},
    "7d": {"amount": "119.00", "description": "Antigravity Manager — Доступ на 1 Неделю", "days": 7, "label": "1 Неделя (119 ₽)"},
    "30d": {"amount": "149.00", "description": "Antigravity Manager — Доступ на 1 Месяц", "days": 30, "label": "1 Месяц (149 ₽)"},
    "365d": {"amount": "399.00", "description": "Antigravity Manager — Доступ на 1 Год", "days": 365, "label": "1 Год (399 ₽)"},
}


def load_yookassa_config() -> Dict[str, str]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "shop_id": os.environ.get("YOOKASSA_SHOP_ID", ""),
        "secret_key": os.environ.get("YOOKASSA_SECRET_KEY", "")
    }


def save_yookassa_config(shop_id: str, secret_key: Optional[str] = None):
    data = load_yookassa_config()
    data["shop_id"] = shop_id.strip()
    if secret_key:
        data["secret_key"] = secret_key.strip()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class YooKassaClient:
    def __init__(self):
        cfg = load_yookassa_config()
        self.shop_id = cfg.get("shop_id", "").strip()
        self.secret_key = cfg.get("secret_key", "").strip()

    def is_configured(self) -> bool:
        return bool(self.shop_id and self.secret_key)

    def set_credentials(self, shop_id: str, secret_key: Optional[str] = None):
        self.shop_id = shop_id.strip()
        if secret_key:
            self.secret_key = secret_key.strip()
        save_yookassa_config(self.shop_id, self.secret_key)

    def _get_headers(self, idempotence_key: Optional[str] = None) -> Dict[str, str]:
        auth_str = f"{self.shop_id}:{self.secret_key}"
        encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json",
        }
        if idempotence_key:
            headers["Idempotence-Key"] = idempotence_key
        return headers

    def create_payment(self, plan_code: str, hwid: str, customer_email: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        if not self.is_configured():
            return False, "Не настроены реквизиты ЮKassa (shopId / secretKey). Укажите их в настройках.", {}

        plan = PLAN_PRICES.get(plan_code)
        if not plan:
            return False, f"Неизвестный тариф: {plan_code}", {}

        idempotence_key = str(uuid.uuid4())
        payload = {
            "amount": {
                "value": plan["amount"],
                "currency": "RUB"
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": "https://yookassa.ru"
            },
            "description": f"{plan['description']} (HWID: {hwid})",
            "metadata": {
                "hwid": hwid,
                "plan_code": plan_code,
            }
        }

        if customer_email and "@" in customer_email:
            payload["receipt"] = {
                "customer": {
                    "email": customer_email.strip()
                },
                "items": [
                    {
                        "description": plan["description"],
                        "quantity": "1.00",
                        "amount": {
                            "value": plan["amount"],
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                        "payment_mode": "full_payment",
                        "payment_subject": "service"
                    }
                ]
            }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(API_URL, data=data_bytes, headers=self._get_headers(idempotence_key), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)

                payment_id = res_json.get("id")
                confirmation = res_json.get("confirmation", {})
                confirmation_url = confirmation.get("confirmation_url", "")
                status = res_json.get("status", "pending")

                return True, "Платёж создан", {
                    "payment_id": payment_id,
                    "confirmation_url": confirmation_url,
                    "status": status,
                    "plan_code": plan_code,
                    "hwid": hwid
                }
        except urllib.error.HTTPError as e:
            try:
                err_text = e.read().decode("utf-8")
                err_json = json.loads(err_text)
                desc = err_json.get("description", str(e))
            except Exception:
                desc = str(e)
            return False, f"Ошибка ЮKassa ({e.code}): {desc}", {}
        except Exception as e:
            return False, f"Ошибка соединения с ЮKassa: {e}", {}

    def check_payment(self, payment_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        if not self.is_configured():
            return False, "Не настроены реквизиты ЮKassa", {}

        url = f"{API_URL}/{payment_id}"
        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")

        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                status = res_json.get("status", "unknown")
                paid = res_json.get("paid", False)
                metadata = res_json.get("metadata", {})

                return True, status, {
                    "payment_id": payment_id,
                    "status": status,
                    "paid": paid,
                    "metadata": metadata
                }
        except Exception as e:
            return False, f"Ошибка проверки статуса: {e}", {}
