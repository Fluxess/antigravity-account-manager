import os
import sys
import time
import json
import uuid
import secrets
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session

# Add root directory to sys.path to access core modules if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server.models import Database, init_db

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "antigravity_admin_secret_99881122")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

PLANS = {
    "3d": {"name": "3 Дня", "days": 3, "price": "69 ₽"},
    "7d": {"name": "1 Неделя", "days": 7, "price": "119 ₽"},
    "30d": {"name": "1 Месяц", "days": 30, "price": "149 ₽"},
    "365d": {"name": "1 Год", "days": 365, "price": "399 ₽"},
}


def generate_online_key(plan_code: str) -> str:
    rnd = secrets.token_hex(6).upper()
    chunks = [rnd[i:i+4] for i in range(0, len(rnd), 4)]
    return f"AGY-{plan_code.upper()}-" + "-".join(chunks)


# =========================================================
#  CLIENT REST API (No Auth required for clients)
# =========================================================

@app.route("/api/ping", methods=["GET"])
def api_ping():
    return jsonify({"status": "ok", "service": "Antigravity Cloud License Server", "time": time.time()})


@app.route("/api/activate", methods=["POST"])
def api_activate():
    """Client calls this to activate a key with their HWID."""
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key", "").strip()
    hwid = data.get("hwid", "").strip()

    if not key or not hwid:
        return jsonify({"success": False, "message": "Требуются key и hwid!"}), 400

    result = Database.activate_license(key, hwid)
    return jsonify(result)


@app.route("/api/check", methods=["POST"])
def api_check():
    """Client calls this periodically to verify their license status."""
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("key", "").strip()
    hwid = data.get("hwid", "").strip()

    if not key or not hwid:
        return jsonify({"is_valid": False, "message": "Требуются key и hwid!"}), 400

    result = Database.check_license(key, hwid)
    return jsonify(result)


@app.route("/api/webhook/yookassa", methods=["POST"])
def yookassa_webhook():
    """Receives YooKassa payment events and automatically issues a key."""
    event_data = request.get_json(force=True, silent=True) or {}
    event_type = event_data.get("event")
    obj = event_data.get("object", {})

    if event_type == "payment.succeeded":
        metadata = obj.get("metadata", {})
        hwid = metadata.get("hwid")
        plan_code = metadata.get("plan_code", "30d")
        plan = PLANS.get(plan_code, PLANS["30d"])
        amount = obj.get("amount", {}).get("value", plan["price"])

        # Generate and save key
        key = generate_online_key(plan_code)
        buyer_note = f"Оплата ЮKassa: {obj.get('id', '')}"
        Database.create_license(key, plan_code, plan["days"], f"{amount} ₽", buyer_note, hwid)

        # If HWID was present, pre-activate
        if hwid:
            Database.activate_license(key, hwid)

        return jsonify({"status": "processed", "key": key}), 200

    return jsonify({"status": "ignored"}), 200


# =========================================================
#  WEB ADMIN DASHBOARD
# =========================================================

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Antigravity License Manager — Панель Управления</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0f1117;
            --panel: #181b24;
            --card: #202430;
            --primary: #4285f4;
            --success: #34a853;
            --danger: #ea4335;
            --warning: #fbbc04;
            --text: #f1f3f4;
            --muted: #9aa0a6;
            --border: #2e3342;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); padding: 24px; }
        .container { max-width: 1200px; margin: 0 auto; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
        h1 { font-size: 20px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .stat-card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 18px; }
        .stat-val { font-size: 26px; font-weight: 700; margin-top: 6px; color: var(--primary); }
        .card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 24px; }
        h2 { font-size: 15px; font-weight: 600; margin-bottom: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
        .form-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
        select, input { background: var(--card); border: 1px solid var(--border); color: var(--text); padding: 10px 14px; border-radius: 6px; font-size: 14px; outline: none; }
        input:focus, select:focus { border-color: var(--primary); }
        button, .btn { background: var(--primary); color: #fff; border: none; padding: 10px 18px; border-radius: 6px; font-weight: 600; font-size: 13px; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
        button:hover, .btn:hover { opacity: 0.9; }
        .btn-danger { background: var(--danger); }
        .btn-success { background: var(--success); }
        .btn-sm { padding: 6px 10px; font-size: 12px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px; }
        th { color: var(--muted); font-weight: 600; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; display: inline-block; }
        .badge-green { background: rgba(52, 168, 83, 0.15); color: #4ade80; border: 1px solid rgba(52, 168, 83, 0.3); }
        .badge-red { background: rgba(234, 67, 53, 0.15); color: #f87171; border: 1px solid rgba(234, 67, 53, 0.3); }
        .badge-yellow { background: rgba(251, 188, 4, 0.15); color: #facc15; border: 1px solid rgba(251, 188, 4, 0.3); }
        .key-code { font-family: monospace; font-weight: 600; color: #60a5fa; background: var(--card); padding: 3px 6px; border-radius: 4px; }
        .actions-cell { display: flex; gap: 6px; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 Antigravity Cloud License Manager</h1>
            <div>
                <a href="{{ url_for('logout') }}" class="btn btn-danger btn-sm">Выйти</a>
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div>Всего ключей</div>
                <div class="stat-val">{{ total_keys }}</div>
            </div>
            <div class="stat-card">
                <div>Активных лицензий</div>
                <div class="stat-val" style="color: var(--success);">{{ active_keys }}</div>
            </div>
            <div class="stat-card">
                <div>Заблокировано</div>
                <div class="stat-val" style="color: var(--danger);">{{ blocked_keys }}</div>
            </div>
        </div>

        <div class="card">
            <h2>➕ Создать новый ключ или пачку для FunPay</h2>
            <form method="POST" action="{{ url_for('admin_create_key') }}">
                <div class="form-row">
                    <select name="plan_code" style="flex: 1;">
                        <option value="3d">3 Дня (69 ₽)</option>
                        <option value="7d">1 Неделя (119 ₽)</option>
                        <option value="30d" selected>1 Месяц (149 ₽)</option>
                        <option value="365d">1 Год (399 ₽)</option>
                    </select>
                    <input type="text" name="hwid" placeholder="HWID (оставьте пустым для FunPay/любого ПК)" style="flex: 1.5;">
                    <input type="text" name="buyer_note" placeholder="Покупатель / Telegram / Номер заказа" style="flex: 1.5;">
                    <input type="number" name="batch_count" value="1" min="1" max="100" style="width: 80px;" title="Количество ключей">
                    <button type="submit">⚡ Сгенерировать</button>
                </div>
            </form>
        </div>

        <div class="card">
            <h2>📋 База лицензий в реальном времени</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Лицензионный ключ</th>
                        <th>Тариф</th>
                        <th>HWID</th>
                        <th>Статус</th>
                        <th>Срок</th>
                        <th>Покупатель</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {% for lic in licenses %}
                    <tr>
                        <td>{{ lic.id }}</td>
                        <td><span class="key-code">{{ lic.license_key }}</span></td>
                        <td><strong>{{ lic.plan_code }}</strong> ({{ lic.price }})</td>
                        <td style="font-family: monospace; font-size: 11px;">{{ lic.hwid or 'Не привязан' }}</td>
                        <td>
                            {% if lic.is_blocked %}
                                <span class="badge badge-red">ЗАБЛОКИРОВАН</span>
                            {% elif not lic.is_active %}
                                <span class="badge badge-yellow">НЕ АКТИВИРОВАН</span>
                            {% elif lic.expires_at and lic.expires_at > now %}
                                <span class="badge badge-green">АКТИВЕН</span>
                            {% else %}
                                <span class="badge badge-red">ИСТЁК</span>
                            {% endif %}
                        </td>
                        <td>
                            {% if lic.expires_at %}
                                {{ lic.expires_at | format_date }}
                            {% else %}
                                —
                            {% endif %}
                        </td>
                        <td style="color: var(--muted);">{{ lic.buyer_note or '—' }}</td>
                        <td class="actions-cell">
                            <form method="POST" action="{{ url_for('admin_toggle_block', key=lic.license_key) }}">
                                <button type="submit" class="btn btn-sm {% if lic.is_blocked %}btn-success{% else %}btn-danger{% endif %}">
                                    {% if lic.is_blocked %}Разблок{% else %}Блок{% endif %}
                                </button>
                            </form>
                            <form method="POST" action="{{ url_for('admin_extend', key=lic.license_key) }}">
                                <button type="submit" class="btn btn-sm" style="background: #374151;">+7 дн</button>
                            </form>
                            <form method="POST" action="{{ url_for('admin_delete', key=lic.license_key) }}" onsubmit="return confirm('Удалить ключ?');">
                                <button type="submit" class="btn btn-sm" style="background: #202430; color: #ef4444;">🗑</button>
                            </form>
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="8" style="text-align: center; color: var(--muted); padding: 30px;">Ключей пока нет. Создайте первый выше!</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Вход в панель управления</title>
    <style>
        body { font-family: sans-serif; background: #0f1117; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .box { background: #181b24; padding: 32px; border-radius: 12px; width: 340px; border: 1px solid #2e3342; text-align: center; }
        input { width: 100%; box-sizing: border-box; padding: 12px; margin: 16px 0; background: #202430; border: 1px solid #2e3342; color: #fff; border-radius: 6px; font-size: 14px; }
        button { width: 100%; padding: 12px; background: #4285f4; border: none; color: #fff; font-weight: bold; border-radius: 6px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="box">
        <h3>Вход в панель продавца</h3>
        <form method="POST">
            <input type="password" name="password" placeholder="Пароль администратора" required autofocus>
            <button type="submit">Войти</button>
        </form>
    </div>
</body>
</html>
"""


@app.template_filter("format_date")
def format_date_filter(timestamp):
    if not timestamp:
        return "—"
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))


@app.route("/", methods=["GET", "POST"])
@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    if not session.get("logged_in"):
        if request.method == "POST":
            pwd = request.form.get("password")
            if pwd == ADMIN_PASSWORD:
                session["logged_in"] = True
                return redirect(url_for("admin_dashboard"))
            return render_template_string(LOGIN_HTML, error="Неверный пароль")
        return render_template_string(LOGIN_HTML)

    licenses = Database.list_licenses()
    total_keys = len(licenses)
    now = time.time()
    active_keys = sum(1 for l in licenses if l["is_active"] and not l["is_blocked"] and l["expires_at"] and l["expires_at"] > now)
    blocked_keys = sum(1 for l in licenses if l["is_blocked"])

    return render_template_string(
        ADMIN_HTML,
        licenses=licenses,
        total_keys=total_keys,
        active_keys=active_keys,
        blocked_keys=blocked_keys,
        now=now
    )


@app.route("/admin/create", methods=["POST"])
def admin_create_key():
    if not session.get("logged_in"):
        return redirect(url_for("admin_dashboard"))

    plan_code = request.form.get("plan_code", "30d")
    hwid = request.form.get("hwid", "").strip() or None
    buyer_note = request.form.get("buyer_note", "").strip() or "Создан вручную"
    batch_count = int(request.form.get("batch_count", 1) or 1)
    plan = PLANS.get(plan_code, PLANS["30d"])

    for _ in range(min(100, max(1, batch_count))):
        key = generate_online_key(plan_code)
        Database.create_license(key, plan_code, plan["days"], plan["price"], buyer_note, hwid)

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/toggle_block/<key>", methods=["POST"])
def admin_toggle_block(key):
    if not session.get("logged_in"):
        return redirect(url_for("admin_dashboard"))
    Database.toggle_block(key)
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/extend/<key>", methods=["POST"])
def admin_extend(key):
    if not session.get("logged_in"):
        return redirect(url_for("admin_dashboard"))
    Database.extend_license(key, extra_days=7)
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete/<key>", methods=["POST"])
def admin_delete(key):
    if not session.get("logged_in"):
        return redirect(url_for("admin_dashboard"))
    Database.delete_license(key)
    return redirect(url_for("admin_dashboard"))


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Antigravity License Server running on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
