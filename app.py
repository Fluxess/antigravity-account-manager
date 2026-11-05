import os
import sys
import time
import ctypes
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional

from core.manager import AccountManager
from core.license import LicenseManager, PLANS, is_debugger_present
from core.yookassa import YooKassaClient, PLAN_PRICES


class ModernTheme:
    BG = "#18191c"
    PANEL_BG = "#1e2025"
    CARD_BG = "#262830"
    CARD_BORDER = "#333642"
    CARD_HOVER = "#2f323c"
    
    PRIMARY = "#4285f4"
    PRIMARY_HOVER = "#5b95f5"
    
    SUCCESS = "#34a853"
    DANGER = "#ea4335"
    WARNING = "#fbbc04"
    PURPLE = "#a142f4"
    
    TEXT_MAIN = "#f1f3f4"
    TEXT_MUTED = "#9aa0a6"
    TEXT_DIM = "#5f6368"
    
    FONT_FAMILY = "Segoe UI"


class AccountManagerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Antigravity Account Manager — Менеджер Аккаунтов")
        self.root.geometry("860x720")
        self.root.minsize(760, 600)
        self.root.configure(bg=ModernTheme.BG)

        self._mutex = self._acquire_single_instance_mutex()

        self.manager = AccountManager()
        self.license_manager = LicenseManager()
        self.yookassa = YooKassaClient()
        
        self._init_styles()
        self._build_header()
        self._build_license_banner()
        self._build_profiles_container()
        self._build_footer()

        self.refresh_license_status()
        self.refresh_profiles()
        self._schedule_status_check()

        if is_debugger_present():
            messagebox.showerror("Ошибка безопасности", "Обнаружена среда отладки / перехвата. Запуск отклонён.")
            self.root.destroy()
            return

        lic = self.license_manager.check_license()
        if not lic["is_active"]:
            self.root.after(300, self.show_activation_modal)

    def _acquire_single_instance_mutex(self):
        try:
            kernel32 = ctypes.windll.kernel32
            mutex = kernel32.CreateMutexW(None, False, "AntigravityAccountManager_AppMutex")
            if kernel32.GetLastError() == 183:
                messagebox.showwarning("Внимание", "Antigravity Account Manager уже запущен на вашем компьютере!")
                sys.exit(0)
            return mutex
        except Exception:
            return None

    def _init_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure("Vertical.TScrollbar",
                        background=ModernTheme.PANEL_BG,
                        troughcolor=ModernTheme.BG,
                        bordercolor=ModernTheme.BG,
                        arrowcolor=ModernTheme.TEXT_MUTED)

    def _build_header(self):
        self.header_frame = tk.Frame(self.root, bg=ModernTheme.PANEL_BG, padx=20, pady=14)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)

        title_frame = tk.Frame(self.header_frame, bg=ModernTheme.PANEL_BG)
        title_frame.pack(fill=tk.X)

        title_label = tk.Label(
            title_frame,
            text="🚀 Antigravity Account Manager",
            font=(ModernTheme.FONT_FAMILY, 15, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.PANEL_BG
        )
        title_label.pack(side=tk.LEFT)

        self.live_status_label = tk.Label(
            title_frame,
            text="Проверка статуса...",
            font=(ModernTheme.FONT_FAMILY, 9),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.PANEL_BG
        )
        self.live_status_label.pack(side=tk.RIGHT)

        # Current account bar
        self.acc_bar = tk.Frame(self.header_frame, bg=ModernTheme.CARD_BG, padx=14, pady=10)
        self.acc_bar.pack(fill=tk.X, pady=(12, 4))

        acc_left = tk.Frame(self.acc_bar, bg=ModernTheme.CARD_BG)
        acc_left.pack(side=tk.LEFT, fill=tk.Y)

        tk.Label(
            acc_left,
            text="Текущий активный логин в Antigravity:",
            font=(ModernTheme.FONT_FAMILY, 9),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.CARD_BG
        ).pack(anchor="w")

        self.current_email_label = tk.Label(
            acc_left,
            text="Загрузка...",
            font=(ModernTheme.FONT_FAMILY, 11, "bold"),
            fg=ModernTheme.PRIMARY,
            bg=ModernTheme.CARD_BG
        )
        self.current_email_label.pack(anchor="w", pady=(2, 0))

        # Quick actions
        btn_box = tk.Frame(self.acc_bar, bg=ModernTheme.CARD_BG)
        btn_box.pack(side=tk.RIGHT)

        self._create_btn(
            btn_box,
            text="💾 Сохранить как профиль",
            bg=ModernTheme.PRIMARY,
            command=self.on_save_current_as_profile
        ).pack(side=tk.LEFT, padx=4)

        self._create_btn(
            btn_box,
            text="➕ Добавить новый аккаунт",
            bg="#2c303b",
            fg=ModernTheme.TEXT_MAIN,
            command=self.on_add_new_account
        ).pack(side=tk.LEFT, padx=4)

        self._create_btn(
            btn_box,
            text="🔄",
            bg="#2c303b",
            fg=ModernTheme.TEXT_MAIN,
            command=self.refresh_profiles
        ).pack(side=tk.LEFT, padx=4)

    def _build_license_banner(self):
        self.lic_frame = tk.Frame(self.root, bg="#161b24", padx=20, pady=8)
        self.lic_frame.pack(fill=tk.X)

        self.lic_label = tk.Label(
            self.lic_frame,
            text="Проверка лицензии...",
            font=(ModernTheme.FONT_FAMILY, 9, "bold"),
            fg=ModernTheme.TEXT_MUTED,
            bg="#161b24"
        )
        self.lic_label.pack(side=tk.LEFT)

        lic_btn_box = tk.Frame(self.lic_frame, bg="#161b24")
        lic_btn_box.pack(side=tk.RIGHT)

        self.online_pay_btn = tk.Button(
            lic_btn_box,
            text="💳 Оплатить (ЮKassa)",
            font=(ModernTheme.FONT_FAMILY, 8, "bold"),
            bg="#34a853",
            fg="#ffffff",
            activebackground="#2d9348",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.show_yookassa_modal
        )
        self.online_pay_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.activate_btn = tk.Button(
            lic_btn_box,
            text="🔑 Ввести ключ",
            font=(ModernTheme.FONT_FAMILY, 8, "bold"),
            bg="#2b3240",
            fg="#8ab4f8",
            activebackground="#374154",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.show_activation_modal
        )
        self.activate_btn.pack(side=tk.RIGHT)

    def _build_profiles_container(self):
        container = tk.Frame(self.root, bg=ModernTheme.BG, padx=20, pady=12)
        container.pack(fill=tk.BOTH, expand=True)

        list_header = tk.Frame(container, bg=ModernTheme.BG)
        list_header.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            list_header,
            text="Сохраненные профили аккаунтов (Пул квот):",
            font=(ModernTheme.FONT_FAMILY, 11, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.BG
        ).pack(side=tk.LEFT)

        self.count_label = tk.Label(
            list_header,
            text="0 профилей",
            font=(ModernTheme.FONT_FAMILY, 9),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.BG
        )
        self.count_label.pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(container, bg=ModernTheme.BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        
        self.scrollable_frame = tk.Frame(self.canvas, bg=ModernTheme.BG)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_footer(self):
        footer = tk.Frame(self.root, bg=ModernTheme.PANEL_BG, padx=20, pady=10)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        self.footer_status = tk.Label(
            footer,
            text="Antigravity путь: " + str(self.manager.find_antigravity_exe() or "Не найден"),
            font=(ModernTheme.FONT_FAMILY, 8),
            fg=ModernTheme.TEXT_MUTED,
            bg=ModernTheme.PANEL_BG
        )
        self.footer_status.pack(side=tk.LEFT)

        ctrl_frame = tk.Frame(footer, bg=ModernTheme.PANEL_BG)
        ctrl_frame.pack(side=tk.RIGHT)

        self._create_btn(
            ctrl_frame,
            text="🚀 Запустить Antigravity",
            bg="#2c303b",
            fg=ModernTheme.TEXT_MAIN,
            command=self.on_launch_antigravity
        ).pack(side=tk.LEFT, padx=4)

        self._create_btn(
            ctrl_frame,
            text="🛑 Закрыть Antigravity",
            bg="#2c303b",
            fg=ModernTheme.DANGER,
            command=self.on_kill_antigravity
        ).pack(side=tk.LEFT, padx=4)

    def _create_btn(self, parent, text, command, bg=ModernTheme.PRIMARY, fg="#ffffff", padx=10, pady=5):
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=ModernTheme.PRIMARY_HOVER,
            activeforeground="#ffffff",
            font=(ModernTheme.FONT_FAMILY, 9, "bold"),
            relief=tk.FLAT,
            bd=0,
            padx=padx,
            pady=pady,
            cursor="hand2"
        )
        return btn

    def refresh_license_status(self):
        lic = self.license_manager.check_license()
        if lic["is_active"]:
            self.lic_label.config(
                text=f"🟢 Подписка активна: {lic['message']} (до {lic['expires_str']})",
                fg=ModernTheme.SUCCESS
            )
            self.activate_btn.config(text="🔑 Продлить ключ")
            self.online_pay_btn.config(text="💳 Продлить онлайн")
        else:
            self.lic_label.config(
                text="🔴 Доступ ограничен: подписка не активирована или истекла",
                fg=ModernTheme.DANGER
            )
            self.activate_btn.config(text="🔑 Ввести ключ")
            self.online_pay_btn.config(text="💳 Купить онлайн")

    def show_activation_modal(self):
        win = tk.Toplevel(self.root)
        win.title("Активация лицензии | Antigravity Account Manager")
        win.geometry("580x560")
        win.minsize(540, 520)
        win.configure(bg="#15171c")
        win.transient(self.root)
        win.grab_set()

        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 580) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 560) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")

        pad_frame = tk.Frame(win, bg="#15171c", padx=24, pady=20)
        pad_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            pad_frame,
            text="🔐 Активация доступа",
            font=(ModernTheme.FONT_FAMILY, 15, "bold"),
            fg="#ffffff",
            bg="#15171c"
        ).pack(anchor="w")

        tk.Label(
            pad_frame,
            text="Для работы с пулом аккаунтов и ротации лимитов оплатите онлайн или введите лицензионный ключ.",
            font=(ModernTheme.FONT_FAMILY, 9),
            fg="#9aa0a6",
            bg="#15171c",
            wraplength=520,
            justify=tk.LEFT
        ).pack(anchor="w", pady=(4, 12))

        # Tariffs Grid
        t_box = tk.LabelFrame(pad_frame, text=" Доступные тарифы ", font=(ModernTheme.FONT_FAMILY, 9, "bold"),
                              fg="#9aa0a6", bg="#15171c", padx=10, pady=8)
        t_box.pack(fill=tk.X, pady=(0, 12))

        t_row = tk.Frame(t_box, bg="#15171c")
        t_row.pack(fill=tk.X)

        tariffs = [
            ("3 Дня", "69 ₽"),
            ("1 Неделя", "119 ₽"),
            ("1 Месяц", "149 ₽"),
            ("1 Год", "399 ₽"),
        ]

        for idx, (period, cost) in enumerate(tariffs):
            cell = tk.Frame(t_row, bg="#20232c", padx=8, pady=8, bd=1, relief=tk.FLAT)
            cell.grid(row=0, column=idx, padx=4, sticky="nsew")
            t_row.grid_columnconfigure(idx, weight=1)

            tk.Label(cell, text=period, font=(ModernTheme.FONT_FAMILY, 9, "bold"), fg="#f1f3f4", bg="#20232c").pack()
            tk.Label(cell, text=cost, font=(ModernTheme.FONT_FAMILY, 10, "bold"), fg="#4285f4", bg="#20232c").pack(pady=(2, 0))

        # Direct Online Pay Button
        online_box = tk.Frame(pad_frame, bg="#15171c")
        online_box.pack(fill=tk.X, pady=(0, 12))

        tk.Button(
            online_box,
            text="💳 ОПЛАТИТЬ ОНЛАЙН (ЮKASSA: СБП / КАРТЫ / SBERPAY)",
            font=(ModernTheme.FONT_FAMILY, 10, "bold"),
            bg="#34a853",
            fg="#ffffff",
            activebackground="#2d9348",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            pady=8,
            cursor="hand2",
            command=lambda: [win.destroy(), self.show_yookassa_modal()]
        ).pack(fill=tk.X)

        # HWID box
        hwid_frame = tk.Frame(pad_frame, bg="#1e2129", padx=12, pady=8)
        hwid_frame.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            hwid_frame,
            text="Ваш Hardware ID (HWID):",
            font=(ModernTheme.FONT_FAMILY, 8, "bold"),
            fg="#9aa0a6",
            bg="#1e2129"
        ).pack(anchor="w")

        hwid_row = tk.Frame(hwid_frame, bg="#1e2129")
        hwid_row.pack(fill=tk.X, pady=(4, 0))

        hwid_val = self.license_manager.hwid
        hwid_lbl = tk.Label(
            hwid_row,
            text=hwid_val,
            font=("Consolas", 10, "bold"),
            fg="#34a853",
            bg="#101216",
            padx=8,
            pady=4
        )
        hwid_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def copy_hwid():
            win.clipboard_clear()
            win.clipboard_append(hwid_val)
            messagebox.showinfo("Скопировано", "Ваш HWID скопирован в буфер обмена!\nОтправьте его продавцу для получения ключа.")

        tk.Button(
            hwid_row,
            text="📋 Копировать",
            font=(ModernTheme.FONT_FAMILY, 9, "bold"),
            bg="#2a2f3d",
            fg="#ffffff",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            command=copy_hwid
        ).pack(side=tk.RIGHT, padx=(8, 0))

        # Key Input Box
        tk.Label(
            pad_frame,
            text="Или введите уже купленный лицензионный ключ:",
            font=(ModernTheme.FONT_FAMILY, 9, "bold"),
            fg="#f1f3f4",
            bg="#15171c"
        ).pack(anchor="w")

        key_entry = tk.Entry(
            pad_frame,
            font=("Consolas", 10),
            bg="#20232c",
            fg="#f1f3f4",
            insertbackground="#ffffff",
            relief=tk.FLAT,
            bd=6
        )
        key_entry.pack(fill=tk.X, pady=(6, 12))

        def do_activate():
            entered = key_entry.get().strip()
            if not entered:
                messagebox.showwarning("Внимание", "Пожалуйста, введите лицензионный ключ!")
                return
            ok, msg = self.license_manager.activate_key(entered)
            if ok:
                messagebox.showinfo("Успешно!", msg)
                win.destroy()
                self.refresh_license_status()
                self.refresh_profiles()
            else:
                messagebox.showerror("Ошибка активации", msg)

        tk.Button(
            pad_frame,
            text="⚡ АКТИВИРОВАТЬ ВВЕДЁННЫЙ КЛЮЧ",
            font=(ModernTheme.FONT_FAMILY, 10, "bold"),
            bg="#4285f4",
            fg="#ffffff",
            activebackground="#5e97f5",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            pady=8,
            cursor="hand2",
            command=do_activate
        ).pack(fill=tk.X)

    def show_yookassa_modal(self):
        """Dedicated interactive YooKassa payment checkout window with auto-activation."""
        pay_win = tk.Toplevel(self.root)
        pay_win.title("Оплата онлайн через ЮKassa | Antigravity Manager")
        pay_win.geometry("540x560")
        pay_win.minsize(500, 520)
        pay_win.configure(bg="#15171c")
        pay_win.transient(self.root)
        pay_win.grab_set()

        pay_win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 540) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 560) // 2
        pay_win.geometry(f"+{max(0, x)}+{max(0, y)}")

        pad = tk.Frame(pay_win, bg="#15171c", padx=24, pady=20)
        pad.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            pad,
            text="💳 Оплата онлайн (ЮKassa)",
            font=(ModernTheme.FONT_FAMILY, 15, "bold"),
            fg="#ffffff",
            bg="#15171c"
        ).pack(anchor="w")

        tk.Label(
            pad,
            text="Выберите тариф. После успешной оплаты в браузере доступ активируется автоматически!",
            font=(ModernTheme.FONT_FAMILY, 9),
            fg="#9aa0a6",
            bg="#15171c",
            wraplength=480,
            justify=tk.LEFT
        ).pack(anchor="w", pady=(4, 14))

        # Radio selection for tariff
        plan_var = tk.StringVar(value="30d")
        t_box = tk.LabelFrame(pad, text=" 1. Выберите тариф ", font=(ModernTheme.FONT_FAMILY, 9, "bold"),
                              fg="#9aa0a6", bg="#15171c", padx=10, pady=8)
        t_box.pack(fill=tk.X, pady=(0, 14))

        for code, info in PLAN_PRICES.items():
            r = tk.Radiobutton(
                t_box,
                text=f"{info['label']} — {info['description'].split('—')[-1].strip()}",
                variable=plan_var,
                value=code,
                font=(ModernTheme.FONT_FAMILY, 9, "bold" if code == "30d" else "normal"),
                fg="#4285f4" if code == "30d" else ModernTheme.TEXT_MAIN,
                bg="#15171c",
                selectcolor="#20232c",
                activebackground="#15171c",
                activeforeground="#ffffff",
                cursor="hand2"
            )
            r.pack(anchor="w", pady=2)

        # Email entry (optional)
        email_box = tk.Frame(pad, bg="#15171c")
        email_box.pack(fill=tk.X, pady=(0, 14))

        tk.Label(
            email_box,
            text="Ваш Email (для чека об оплате):",
            font=(ModernTheme.FONT_FAMILY, 9),
            fg="#9aa0a6",
            bg="#15171c"
        ).pack(anchor="w")

        email_entry = tk.Entry(
            email_box,
            font=("Segoe UI", 10),
            bg="#20232c",
            fg="#f1f3f4",
            insertbackground="#ffffff",
            relief=tk.FLAT,
            bd=5
        )
        email_entry.pack(fill=tk.X, pady=(4, 0))

        # Status text during polling
        status_lbl = tk.Label(
            pad,
            text="",
            font=(ModernTheme.FONT_FAMILY, 9, "bold"),
            fg=ModernTheme.WARNING,
            bg="#15171c",
            wraplength=480
        )
        status_lbl.pack(pady=(0, 10))

        # Action button
        pay_btn = tk.Button(
            pad,
            text="🚀 ПЕРЕЙТИ К ОПЛАТЕ В ЮKASSA",
            font=(ModernTheme.FONT_FAMILY, 10, "bold"),
            bg="#34a853",
            fg="#ffffff",
            activebackground="#2d9348",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            pady=9,
            cursor="hand2"
        )
        pay_btn.pack(fill=tk.X)

        polling_active = [False]

        def on_close():
            polling_active[0] = False
            pay_win.destroy()

        pay_win.protocol("WM_DELETE_WINDOW", on_close)

        def start_payment():
            if not self.yookassa.is_configured():
                messagebox.showerror(
                    "ЮKassa не настроена",
                    "Внимание: shopId ЮKassa пока не указан!\n\n"
                    "Продавец должен сохранить shopId в настройках админки или файле yookassa_config.json."
                )
                return

            chosen_plan = plan_var.get()
            email = email_entry.get().strip() or None
            hwid = self.license_manager.hwid

            pay_btn.config(state=tk.DISABLED, text="Создание платежа...", bg="#555555")
            status_lbl.config(text="Инициализация сессии оплаты ЮKassa...", fg=ModernTheme.PRIMARY)

            ok, msg, data = self.yookassa.create_payment(chosen_plan, hwid, email)
            if not ok:
                pay_btn.config(state=tk.NORMAL, text="🚀 ПЕРЕЙТИ К ОПЛАТЕ В ЮKASSA", bg="#34a853")
                status_lbl.config(text=f"Ошибка: {msg}", fg=ModernTheme.DANGER)
                return

            payment_id = data["payment_id"]
            url = data["confirmation_url"]

            # Open payment page in browser
            webbrowser.open(url)
            status_lbl.config(
                text="⏳ Страница оплаты открыта в браузере.\nОплатите через СБП, Mir Pay или картой.\nОжидаем подтверждения от банка...",
                fg=ModernTheme.WARNING
            )
            pay_btn.config(text="Ожидание оплаты...", bg="#4285f4")

            polling_active[0] = True

            def poll_status():
                start_t = time.time()
                while polling_active[0] and (time.time() - start_t < 900):  # 15 minutes timeout
                    time.sleep(3)
                    if not polling_active[0]:
                        break

                    chk_ok, current_status, pdata = self.yookassa.check_payment(payment_id)
                    if not chk_ok:
                        continue

                    if current_status == "succeeded" or pdata.get("paid"):
                        # Payment successful! Generate key and activate
                        generated_key = LicenseManager.generate_key(chosen_plan, hwid)
                        act_ok, act_msg = self.license_manager.activate_key(generated_key)
                        
                        def on_success():
                            polling_active[0] = False
                            pay_win.destroy()
                            self.refresh_license_status()
                            self.refresh_profiles()
                            messagebox.showinfo(
                                "🎉 Оплата прошла успешно!",
                                f"Платеж подтвержден ЮKassa!\n\nЛицензия успешно активирована на вашем ПК.\nПриятного использования Antigravity!"
                            )
                        self.root.after(0, on_success)
                        break

                    elif current_status == "canceled":
                        def on_cancel():
                            status_lbl.config(text="❌ Платеж был отменён пользователем или банком.", fg=ModernTheme.DANGER)
                            pay_btn.config(state=tk.NORMAL, text="Попробовать снова", bg="#34a853")
                        self.root.after(0, on_cancel)
                        break

            threading.Thread(target=poll_status, daemon=True).start()

        pay_btn.config(command=start_payment)

    def _require_license(self) -> bool:
        lic = self.license_manager.check_license()
        if not lic["is_active"]:
            self.show_activation_modal()
            return False
        return True

    def refresh_profiles(self):
        curr = self.manager.detect_current_account()
        self.current_email_label.config(text=curr["email"] or "Не авторизован")
        
        is_running = curr["is_running"]
        status_text = "🟢 Antigravity запущен" if is_running else "⚪ Antigravity не запущен"
        status_color = ModernTheme.SUCCESS if is_running else ModernTheme.TEXT_MUTED
        self.live_status_label.config(text=status_text, fg=status_color)

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        profiles = self.manager.list_profiles()
        self.count_label.config(text=f"Всего: {len(profiles)} профилей")

        if not profiles:
            empty_box = tk.Frame(self.scrollable_frame, bg=ModernTheme.CARD_BG, padx=24, pady=28)
            empty_box.pack(fill=tk.X, pady=16)

            tk.Label(
                empty_box,
                text="У вас пока нет сохраненных профилей",
                font=(ModernTheme.FONT_FAMILY, 12, "bold"),
                fg=ModernTheme.TEXT_MAIN,
                bg=ModernTheme.CARD_BG
            ).pack()

            tk.Label(
                empty_box,
                text="1. Нажмите «💾 Сохранить как профиль», чтобы зафиксировать текущий аккаунт.\n"
                     "2. Нажмите «➕ Добавить новый аккаунт», чтобы подключить второй Google-аккаунт для ротации квот.",
                font=(ModernTheme.FONT_FAMILY, 9),
                fg=ModernTheme.TEXT_MUTED,
                bg=ModernTheme.CARD_BG,
                justify=tk.CENTER
            ).pack(pady=8)
            return

        for p in profiles:
            self._render_profile_card(p)

    def _render_profile_card(self, p: dict):
        pid = p["id"]
        is_active = p.get("is_active", False)
        status = p.get("quota_status", "ready")
        
        card = tk.Frame(
            self.scrollable_frame,
            bg=ModernTheme.CARD_BG,
            highlightthickness=1,
            highlightbackground=ModernTheme.PRIMARY if is_active else ModernTheme.CARD_BORDER,
            padx=16,
            pady=12
        )
        card.pack(fill=tk.X, pady=6)

        left = tk.Frame(card, bg=ModernTheme.CARD_BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        top_row = tk.Frame(left, bg=ModernTheme.CARD_BG)
        top_row.pack(fill=tk.X)

        tk.Label(
            top_row,
            text=p.get("name", "Профиль"),
            font=(ModernTheme.FONT_FAMILY, 11, "bold"),
            fg=ModernTheme.TEXT_MAIN,
            bg=ModernTheme.CARD_BG
        ).pack(side=tk.LEFT)

        badge_text, badge_color = self._get_status_badge(status, is_active)
        badge = tk.Label(
            top_row,
            text=f" {badge_text} ",
            font=(ModernTheme.FONT_FAMILY, 8, "bold"),
            fg="#ffffff",
            bg=badge_color,
            padx=4,
            pady=1
        )
        badge.pack(side=tk.LEFT, padx=8)

        email_lbl = tk.Label(
            left,
            text=f"✉ {p.get('email', 'Неизвестно')}",
            font=(ModernTheme.FONT_FAMILY, 9),
            fg=ModernTheme.PRIMARY if is_active else ModernTheme.TEXT_MUTED,
            bg=ModernTheme.CARD_BG
        )
        email_lbl.pack(anchor="w", pady=(3, 0))

        notes = p.get("notes", "").strip()
        if notes:
            tk.Label(
                left,
                text=f"📝 {notes}",
                font=(ModernTheme.FONT_FAMILY, 8),
                fg=ModernTheme.TEXT_DIM,
                bg=ModernTheme.CARD_BG
            ).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(card, bg=ModernTheme.CARD_BG)
        right.pack(side=tk.RIGHT)

        if not is_active:
            self._create_btn(
                right,
                text="⚡ Переключить",
                bg=ModernTheme.PRIMARY,
                command=lambda id_=pid: self.on_switch_profile(id_)
            ).pack(side=tk.LEFT, padx=3)
        else:
            tk.Label(
                right,
                text="✓ Выбран",
                font=(ModernTheme.FONT_FAMILY, 9, "bold"),
                fg=ModernTheme.SUCCESS,
                bg=ModernTheme.CARD_BG,
                padx=8
            ).pack(side=tk.LEFT)

        status_toggle_btn = self._create_btn(
            right,
            text="🔴 Исчерпан" if status != "exhausted" else "🟢 Готов",
            bg="#363942",
            fg=ModernTheme.TEXT_MAIN,
            command=lambda id_=pid, s=status: self.on_toggle_status(id_, s)
        )
        status_toggle_btn.pack(side=tk.LEFT, padx=3)

        self._create_btn(
            right,
            text="✏",
            bg="#363942",
            fg=ModernTheme.TEXT_MUTED,
            command=lambda id_=pid: self.on_edit_profile(id_)
        ).pack(side=tk.LEFT, padx=2)

        self._create_btn(
            right,
            text="🗑",
            bg="#363942",
            fg=ModernTheme.DANGER,
            command=lambda id_=pid: self.on_delete_profile(id_)
        ).pack(side=tk.LEFT, padx=2)

    def _get_status_badge(self, status: str, is_active: bool):
        if is_active:
            return ("АКТИВЕН В СЕССИИ", ModernTheme.SUCCESS)
        if status == "exhausted":
            return ("ЛИМИТ ИСЧЕРПАН", ModernTheme.DANGER)
        if status == "premium":
            return ("AI PREMIUM", ModernTheme.PRIMARY)
        return ("ГОТОВ К РАБОТЕ", "#4a4d57")

    def on_save_current_as_profile(self):
        if not self._require_license():
            return

        curr = self.manager.detect_current_account()
        email = curr["email"]

        name = simpledialog.askstring("Сохранить профиль", "Введите название профиля:",
                                      initialvalue=f"Аккаунт {email.split('@')[0] if '@' in email else '1'}")
        if not name:
            return

        notes = simpledialog.askstring("Заметка к профилю", "Заметка (например, «Основной», «Google One», лимиты):",
                                       initialvalue="") or ""

        if self.manager.is_antigravity_running():
            msg = ("Для надёжной фиксации сессии и куки рекомендуется на 2 секунды закрыть Antigravity.\n\n"
                   "Закрыть Antigravity и сохранить профиль?")
            if messagebox.askyesno("Сохранение профиля", msg):
                self.manager.close_antigravity()
            else:
                return

        profile_id = f"prof_{int(time.time())}"
        try:
            self.manager.save_current_as_profile(profile_id, name, notes)
            messagebox.showinfo("Успешно", f"Профиль «{name}» успешно сохранен!")
            self.refresh_profiles()
            self.manager.launch_antigravity()
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", str(e))

    def on_switch_profile(self, profile_id: str):
        if not self._require_license():
            return

        profiles = {p["id"]: p for p in self.manager.list_profiles()}
        target = profiles.get(profile_id, {})
        target_name = target.get("name", "Выбранный профиль")

        if self.manager.is_antigravity_running():
            ans = messagebox.askyesno(
                "Переключение профиля",
                f"Antigravity сейчас запущен.\n\nПереключить на «{target_name}» и перезапустить Antigravity?"
            )
            if not ans:
                return

        try:
            self.manager.switch_profile(profile_id, restart_app=True)
            self.refresh_profiles()
            messagebox.showinfo("Готово", f"Успешно переключено на «{target_name}»!\nAntigravity перезапускается.")
        except Exception as e:
            messagebox.showerror("Ошибка переключения", str(e))

    def on_toggle_status(self, profile_id: str, current_status: str):
        if not self._require_license():
            return
        new_status = "ready" if current_status == "exhausted" else "exhausted"
        self.manager.update_profile_status(profile_id, new_status)
        self.refresh_profiles()

    def on_edit_profile(self, profile_id: str):
        profiles = {p["id"]: p for p in self.manager.list_profiles()}
        target = profiles.get(profile_id, {})
        
        new_name = simpledialog.askstring("Редактировать имя", "Имя профиля:", initialvalue=target.get("name", ""))
        if new_name is None:
            return
        
        new_notes = simpledialog.askstring("Редактировать заметку", "Заметка / Сброс квоты:", initialvalue=target.get("notes", ""))
        if new_notes is None:
            return

        self.manager.settings["profiles"][profile_id]["name"] = new_name
        self.manager.settings["profiles"][profile_id]["notes"] = new_notes
        self.manager._save_settings()
        self.refresh_profiles()

    def on_delete_profile(self, profile_id: str):
        profiles = {p["id"]: p for p in self.manager.list_profiles()}
        target = profiles.get(profile_id, {})
        name = target.get("name", profile_id)

        if messagebox.askyesno("Удаление", f"Вы уверены, что хотите удалить профиль «{name}»?"):
            self.manager.delete_profile(profile_id)
            self.refresh_profiles()

    def on_add_new_account(self):
        if not self._require_license():
            return

        msg = (
            "Мастер добавления нового Google-аккаунта:\n\n"
            "1. Приложение сохранит текущую сессию в бэкап.\n"
            "2. Antigravity закроется и откроется с чистым экраном авторизации.\n"
            "3. Вы входите во второй Google-аккаунт.\n"
            "4. Возвращаетесь сюда и нажимаете «💾 Сохранить как профиль»!\n\n"
            "Начать процедуру подключения нового аккаунта?"
        )
        if not messagebox.askyesno("Новый аккаунт", msg):
            return

        try:
            self.manager.prepare_clean_login_slot()
            messagebox.showinfo(
                "Окно авторизации открыто",
                "Antigravity запущен с чистой авторизацией.\n\n"
                "Войдите в ваш второй Google аккаунт в окне Antigravity, а затем нажмите кнопку «💾 Сохранить как профиль» в этом менеджере!"
            )
            self.refresh_profiles()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def on_launch_antigravity(self):
        try:
            self.manager.launch_antigravity()
            time.sleep(1)
            self.refresh_profiles()
        except Exception as e:
            messagebox.showerror("Ошибка запуска", str(e))

    def on_kill_antigravity(self):
        if self.manager.close_antigravity():
            messagebox.showinfo("Остановлен", "Процессы Antigravity успешно закрыты.")
        else:
            messagebox.showwarning("Внимание", "Не удалось полностью остановить процессы.")
        self.refresh_profiles()

    def _schedule_status_check(self):
        if is_debugger_present():
            self.root.destroy()
            return

        is_running = self.manager.is_antigravity_running()
        status_text = "🟢 Antigravity запущен" if is_running else "⚪ Antigravity не запущен"
        status_color = ModernTheme.SUCCESS if is_running else ModernTheme.TEXT_MUTED
        self.live_status_label.config(text=status_text, fg=status_color)
        self.root.after(3000, self._schedule_status_check)


if __name__ == "__main__":
    root = tk.Tk()
    app = AccountManagerApp(root)
    root.mainloop()
