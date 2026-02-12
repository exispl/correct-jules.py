import customtkinter as ctk
import tkinter as tk
import threading
import queue
import time
import difflib
import keyboard
import pystray
from PIL import Image, ImageDraw
import os

from corr_config import cfg, gui_queue, FONTS
from corr_ai import ai
from corr_gui import BubbleButton, HistoryItem, ReviewPopup
from corr_worker import worker

# --- MAIN APP ---
class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Assistant Pro")
        self.geometry("1200x800")
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.update_theme()

        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)

        self.tabs = {
            "Dash": self.tabview.add("Dashboard"),
            "Hist": self.tabview.add("Historia"),
            "Snip": self.tabview.add("Snippety"),
            "Short": self.tabview.add("Skróty"),
            "Sett": self.tabview.add("Ustawienia"),
        }

        # Init Modules
        self.setup_dash()
        self.setup_hist()
        self.setup_snip()
        self.setup_short()
        self.setup_sett()

        # Footer
        ver = cfg.get_version()
        self.status = ctk.CTkLabel(self, text=f"Gotowy | {ver}", anchor="w", height=30, font=("Arial", 12))
        self.status.grid(row=1, column=0, sticky="ew", padx=10)

        if not cfg.config.get("api_key"):
            self.status.configure(text="⚠️ Skonfiguruj klucz API w ustawieniach!", text_color="#ffcc00")

        if not cfg.user_profile.get("logged_in"):
            self.show_login_overlay()
        else:
            self.show_user_badge()

        # Background tasks
        self.check_queue()
        self.register_hotkeys()
        self.setup_tray()

    def check_queue(self):
        try:
            while True:
                msg, data = gui_queue.get_nowait()
                if msg == "POPUP":
                    ReviewPopup(self, data['action'], data['org'], data['res'], data['dur'])
                elif msg == "REFRESH":
                    self.refresh_hist()
                    self.refresh_dash()
                elif msg == "STATUS":
                    self.status.configure(text=data['text'], text_color=data.get('color', 'white'))
        except queue.Empty: pass
        finally: self.after(200, self.check_queue)

    # --- TEST ZONE (DASHBOARD) ---
    def setup_test_zone(self, parent, row):
        parent.grid_rowconfigure(row, weight=1)
        colors = cfg.get_theme_colors()
        font_base = (cfg.config["font_family"], colors.get("font_size_base", 14))
        font_large = (cfg.config["font_family"], colors.get("font_size_large", 18))

        # Container
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=10, pady=5)
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(2, weight=1) # Output expands

        # Input Area
        input_label_frame = ctk.CTkFrame(f, fg_color="transparent")
        input_label_frame.grid(row=0, column=0, sticky="ew", padx=5)

        # Tools Icons (Copy, Paste History) - Much Bigger Icons
        ctk.CTkButton(input_label_frame, text="📋", width=60, height=50, fg_color=colors.get("button_color"), hover_color=colors.get("button_hover"),
                      text_color="black", font=("Arial", 24), command=lambda: self.copy_to_clipboard(self.test_in)).pack(side="right", padx=5)

        ctk.CTkButton(input_label_frame, text="🗂️", width=60, height=50, fg_color=colors.get("button_color"), hover_color=colors.get("button_hover"),
                      text_color="black", font=("Arial", 24), command=self.trigger_win_v).pack(side="right", padx=5)

        self.test_in = ctk.CTkTextbox(f, height=120, font=font_large,
                                      fg_color=colors.get("input_bg"), text_color=colors.get("text_color"))
        self.test_in.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        # Focus input by default
        self.after(200, lambda: self.test_in.focus_set())

        # Action Buttons Frame
        btn_frame = ctk.CTkFrame(f, fg_color="transparent")
        btn_frame.grid(row=1, column=1, sticky="nw", padx=5, pady=5)

        actions = [
            ("✨ Korekta", "CORRECT"),
            ("🌍 Tłumacz", "TRANSLATE"),
            ("📝 Streszcz", "SUMMARIZE"),
            ("👔 Ton", "TONE_CHANGE"),
            ("💡 Wyjaśnij", "EXPLAIN")
        ]

        for label, code in actions:
            ctk.CTkButton(btn_frame, text=label, width=140, height=40, font=(font_base[0], font_base[1], "bold"),
                          fg_color=colors.get("button_color"),
                          hover_color=colors.get("button_hover"), text_color="black", # Button text usually black on bright buttons
                          command=lambda c=code: self.run_dashboard_action(c)).pack(pady=4)

        # Output Area
        output_label_frame = ctk.CTkFrame(f, fg_color="transparent")
        output_label_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=(10,0))
        ctk.CTkLabel(output_label_frame, text="Wynik:", text_color=colors.get("text_color"), font=font_base).pack(side="left")

        ctk.CTkButton(output_label_frame, text="📋", width=50, height=35, fg_color=colors.get("button_color"), hover_color=colors.get("button_hover"),
                      text_color="black", font=("Arial", 20), command=lambda: self.copy_to_clipboard(self.out_text)).pack(side="right", padx=5)

        self.out_frame = ctk.CTkFrame(f, fg_color=colors.get("history_bg"))
        self.out_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)

        self.out_text = tk.Text(self.out_frame, bg=colors.get("history_bg"), fg=colors.get("text_color"),
                                font=font_large,
                                relief="flat", wrap="word", padx=10, pady=10)
        self.out_text.pack(fill="both", expand=True)

        # Context Menu
        self.menu = tk.Menu(self, tearoff=0, bg=colors.get("frame_color"), fg=colors.get("text_color"))

    def copy_to_clipboard(self, widget):
        try:
            txt = widget.get("0.0", "end").strip()
            pyperclip.copy(txt)
            self.status.configure(text="Skopiowano do schowka!", text_color="green")
        except: pass

    def trigger_win_v(self):
        colors = cfg.get_theme_colors()
        keyboard.send('windows+v')
        self.status.configure(text="Otwarto historię schowka (Win+V)", text_color=colors.get("accent_text"))

    def show_user_badge(self):
        f = self.tabs["Dash"]
        colors = cfg.get_theme_colors()

        name = cfg.user_profile.get("name", "Gość")
        badge = ctk.CTkLabel(f, text=f"👤 {name}", text_color=colors.get("text_color"), fg_color=colors.get("frame_color"), corner_radius=10)
        badge.place(relx=0.95, rely=0.02, anchor="ne")
        badge.bind("<Button-1>", lambda e: self.logout())

    def logout(self):
        cfg.user_profile = {"name": "Gość", "email": "", "photo": "", "logged_in": False}
        cfg.save_profile()
        self.status.configure(text="Wylogowano.", text_color="yellow")
        for w in self.tabs["Dash"].place_slaves(): w.destroy()
        self.show_login_overlay()

    def show_login_overlay(self):
        self.login_frame = ctk.CTkFrame(self, fg_color="black") # Overlay
        self.login_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        c = ctk.CTkFrame(self.login_frame, fg_color="#333", corner_radius=20, width=400, height=300)
        c.place(relx=0.5, rely=0.5, anchor="center")
        c.pack_propagate(False)

        ctk.CTkLabel(c, text="AI Assistant Pro", font=("Arial", 24, "bold"), text_color="white").pack(pady=20)
        ctk.CTkLabel(c, text="Zaloguj się, aby synchronizować ustawienia", text_color="gray").pack()

        btn_g = ctk.CTkButton(c, text="   Zaloguj przez Google   ", fg_color="white", text_color="black", hover_color="#f0f0f0",
                              height=40, font=("Arial", 14), command=self.perform_fake_login)
        btn_g.pack(pady=40)

        ctk.CTkButton(c, text="Pomiń (Tryb Gościa)", fg_color="transparent", text_color="gray", hover=False, command=self.skip_login).pack(side="bottom", pady=20)
        self.perform_fake_login()

    def perform_fake_login(self):
        if self.login_frame:
            self.login_frame.destroy()

        cfg.user_profile = {
            "name": "Kamil Kowalski",
            "email": "kamil@kowalczyk.com",
            "photo": "",
            "logged_in": True
        }
        cfg.save_profile()
        self.show_user_badge()
        self.status.configure(text="Zalogowano jako Kamil", text_color="green")

    def skip_login(self):
        self.login_frame.destroy()
        self.status.configure(text="Tryb Gościa.", text_color="gray")

    def run_dashboard_action(self, action_code):
        txt = self.test_in.get("0.0", "end").strip()
        if not txt: return
        self.status.configure(text=f"AI pracuje ({action_code})...", text_color="yellow")
        threading.Thread(target=self._thread_test, args=(txt, action_code), daemon=True).start()

    def _thread_test(self, txt, action_code):
        try:
            res, dur = ai.process_text(action_code, txt)
            if res:
                if action_code in ["CORRECT", "TONE_CHANGE"]:
                    self.after(0, lambda: self.render_bubbles(txt, res, action_code))
                else:
                    self.after(0, lambda: self.render_text(res))
            else:
                gui_queue.put(("STATUS", {"text": f"Błąd: {dur}", "color": "red"}))
        finally:
            self.after(0, lambda: self.status.configure(text="Gotowe.", text_color="green"))

    def render_text(self, text):
        self.out_text.delete("1.0", "end")
        self.out_text.insert("end", text)
        cfg.add_history_entry("OTHER", "", text, 0)

    def render_bubbles(self, original, result, action_type="CORRECT"):
        self.out_text.delete("1.0", "end")
        orig_words = original.split()
        res_words = result.split()
        matcher = difflib.SequenceMatcher(None, orig_words, res_words)

        diffs = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                segment = " ".join(res_words[j1:j2]) + " "
                self.out_text.insert("end", segment)
            elif tag in ('replace', 'insert'):
                new_phrase = " ".join(res_words[j1:j2])
                old_phrase = " ".join(orig_words[i1:i2])
                btn = BubbleButton(self.out_text, text=new_phrase, original_text=old_phrase)
                btn.bind("<Button-1>", lambda e, b=btn: self.show_bubble_menu(e, b))
                btn.bind("<Button-3>", lambda e, b=btn: self.show_bubble_menu(e, b))
                self.out_text.window_create("end", window=btn)
                self.out_text.insert("end", " ")

                if old_phrase:
                    diffs.append({"old": old_phrase, "new": new_phrase})

        cfg.add_history_entry(action_type, original, result, 0, diffs=diffs)

    def show_bubble_menu(self, event, btn):
        self.menu.delete(0, "end")
        new_text = btn.cget('text')
        old_text = btn.original_text

        self.menu.add_command(label=f"✅ Akceptuj: '{new_text}'",
                              command=lambda: self.resolve_bubble(btn, new_text))

        if old_text:
             self.menu.add_command(label=f"⚡ Dodaj do Auto-Replace: '{old_text}' -> '{new_text}'",
                              command=lambda: self.add_to_autoreplace(btn, old_text, new_text))

        self.menu.add_separator()

        if old_text:
            self.menu.add_command(label=f"↩️ Przywróć: '{old_text}'",
                                  command=lambda: self.resolve_bubble(btn, old_text, is_revert=True))
            self.menu.add_command(label=f"🚫 Ignoruj '{old_text}' (Nigdy nie zmieniaj)",
                                  command=lambda: self.ignore_word(btn, old_text))

        self.menu.add_separator()
        self.menu.add_command(label="✏️ Edytuj ręcznie...", command=lambda: self.manual_bubble_edit(btn))
        self.menu.tk_popup(event.x_root, event.y_root)

    def resolve_bubble(self, btn, text, is_revert=False):
        colors = cfg.get_theme_colors()
        txt_col = colors.get("text_color")
        if is_revert:
            btn.configure(text=text, fg_color="transparent", hover=False, text_color=txt_col)
        else:
            btn.configure(fg_color="transparent", hover=False, text_color=txt_col)

    def add_to_autoreplace(self, btn, old, new):
        cfg.auto_replace.add_replacement(old, new)
        self.resolve_bubble(btn, new)
        self.status.configure(text=f"Dodano do Auto-Replace: {old} -> {new}", text_color="green")

    def ignore_word(self, btn, old):
        cfg.auto_replace.add_ignore(old)
        self.resolve_bubble(btn, old, is_revert=True)
        self.status.configure(text=f"Zignorowano: {old}", text_color="yellow")

    def manual_bubble_edit(self, btn):
        d = ctk.CTkInputDialog(text="Wpisz poprawną wersję:", title="Edycja")
        res = d.get_input()
        if res:
            btn.configure(text=res)

    # --- SHORTCUTS ---
    def setup_short(self):
        f = self.tabs["Short"]
        colors = cfg.get_theme_colors()

        ctk.CTkLabel(f, text="Twoje Skróty (Visual Reference)", font=("Arial", 16, "bold"), text_color=colors.get("text_color")).pack(pady=10)

        scroll = ctk.CTkScrollableFrame(f, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        std_frame = ctk.CTkFrame(scroll, fg_color=colors.get("frame_color"))
        std_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(std_frame, text="System Windows", font=("Arial", 14, "bold"), text_color=colors.get("accent_text")).pack(pady=5)

        keys = [
            ("WIN + V", "Historia Schowka"),
            ("WIN + SHIFT + S", "Zrzut Ekranu"),
            ("WIN + .", "Panel Emoji"),
            ("CTRL + SHIFT + ESC", "Menedżer Zadań"),
            ("WIN + L", "Zablokuj Ekran")
        ]
        for k, d in keys:
            r = ctk.CTkFrame(std_frame, fg_color="transparent")
            r.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(r, text=k, font=("Consolas", 12, "bold"), width=150, anchor="e", text_color=colors.get("text_color")).pack(side="left")
            ctk.CTkLabel(r, text=d, text_color="gray", anchor="w").pack(side="left", padx=10)

        target_dir = r"C:\Users\kamil\Pictures\Screenshots\Shortuts"
        if os.path.exists(target_dir):
            files = [f for f in os.listdir(target_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            if files:
                ctk.CTkLabel(scroll, text="Wykryte w katalogu:", font=("Arial", 14, "bold"), text_color=colors.get("accent_text")).pack(pady=(20,5))
                for file in files:
                    f_card = ctk.CTkFrame(scroll, fg_color=colors.get("frame_color"))
                    f_card.pack(fill="x", padx=10, pady=2)
                    ctk.CTkLabel(f_card, text=f"🖼️ {file}", text_color=colors.get("text_color")).pack(side="left", padx=10, pady=5)
            else:
                ctk.CTkLabel(scroll, text=f"Brak obrazków w:\n{target_dir}", text_color="gray").pack(pady=20)

    # --- SNIPPETS ---
    def setup_snip(self):
        f = self.tabs["Snip"]
        colors = cfg.get_theme_colors()
        font_base = (cfg.config["font_family"], colors.get("font_size_base", 14))

        # Grid of Icons (Top)
        icons_path = cfg.config.get("icons_path", "")
        if icons_path and os.path.exists(icons_path):
            ctk.CTkLabel(f, text="Szybkie Akcje (Ikony)", font=("Arial", 16, "bold"), text_color=colors.get("accent_text")).pack(pady=5)
            icon_frame = ctk.CTkScrollableFrame(f, height=150, fg_color="transparent", orientation="horizontal")
            icon_frame.pack(fill="x", padx=5, pady=5)

            try:
                files = [x for x in os.listdir(icons_path) if x.lower().endswith((".png", ".ico", ".jpg"))]
                for file in files:
                    # Simple button for each file
                    # Ideally we would load the image, but CTkImage requires PIL which is fine
                    # But for now let's just make square buttons with filenames if loading fails
                    name = os.path.splitext(file)[0]
                    btn = ctk.CTkButton(icon_frame, text=name, width=80, height=80,
                                        fg_color=colors.get("button_color"), text_color="black",
                                        command=lambda n=name: self.run_icon_action(n))
                    btn.pack(side="left", padx=5)
            except Exception as e:
                ctk.CTkLabel(icon_frame, text=f"Błąd ładowania ikon: {e}").pack()

        # Tools
        tool_bar = ctk.CTkFrame(f, fg_color="transparent")
        tool_bar.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(tool_bar, text="➕ Nowy Snippet", command=self.add_snippet_dialog,
                      fg_color=colors.get("button_color"), text_color="black").pack(side="left")
        ctk.CTkLabel(tool_bar, text="Wpisz skrót (np. ;mail) -> Spacja", text_color="gray").pack(side="right")

        # List
        self.snip_scroll = ctk.CTkScrollableFrame(f)
        self.snip_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.refresh_snip()

    def run_icon_action(self, name):
        # Trigger snippet if exists, or just type the name?
        # User requirement implies icons are snippets.
        # Let's assume the icon name matches a snippet key?
        # Or maybe it just types the name?
        # Let's try to find a snippet with that key.
        if name in cfg.snippets.snippets:
             # Execute snippet
             data = cfg.snippets.snippets[name]
             worker._execute_snippet(name, data)
        else:
             self.status.configure(text=f"Brak snippetu dla: {name}", text_color="yellow")

    def refresh_snip(self):
        for w in self.snip_scroll.winfo_children(): w.destroy()
        colors = cfg.get_theme_colors()

        for key, data in cfg.snippets.snippets.items():
            fr = ctk.CTkFrame(self.snip_scroll, fg_color=colors.get("history_bg"))
            fr.pack(fill="x", pady=2, padx=5)

            t = data.get("type", "text")
            icon = "📝" if t == "text" else ("🚀" if t == "app" else "🤖")

            ctk.CTkLabel(fr, text=f"{icon} {key}", font=("Consolas", 14, "bold"), text_color=colors.get("accent_text"), width=120, anchor="w").pack(side="left", padx=10)

            content_prev = data['content'][:40] + "..." if len(data['content']) > 40 else data['content']
            ctk.CTkLabel(fr, text=content_prev, text_color=colors.get("text_color"), anchor="w").pack(side="left", fill="x", expand=True)

            hk = data.get("hotkey")
            if hk:
                ctk.CTkLabel(fr, text=f"[{hk}]", text_color="gray", font=("Consolas", 11)).pack(side="left", padx=10)

            ctk.CTkButton(fr, text="🗑️", width=30, fg_color="transparent", text_color="red", hover_color=colors.get("frame_color"),
                          command=lambda k=key: self.delete_snippet(k)).pack(side="right", padx=5)
            ctk.CTkButton(fr, text="✏️", width=30, fg_color="transparent", text_color=colors.get("text_color"), hover_color=colors.get("frame_color"),
                          command=lambda k=key: self.edit_snippet(k)).pack(side="right", padx=5)

    def add_snippet_dialog(self):
        self._snippet_dialog()

    def edit_snippet(self, key):
        data = cfg.snippets.snippets[key]
        self._snippet_dialog(key, data['content'], data.get('type', 'text'), data.get('hotkey', ''))

    def delete_snippet(self, key):
        cfg.snippets.remove_snippet(key)
        self.refresh_snip()
        self.status.configure(text=f"Usunięto snippet: {key}", text_color="red")

    def _snippet_dialog(self, edit_key=None, edit_content=None, edit_type="text", edit_hotkey=""):
        d = ctk.CTkToplevel(self)
        d.title("Edytor Snippetu")
        d.geometry("450x550")
        d.attributes("-topmost", True)

        colors = cfg.get_theme_colors()
        d.configure(fg_color=colors.get("fg_color"))

        ctk.CTkLabel(d, text="Skrót tekstowy (np. ;tel):", text_color=colors.get("text_color")).pack(anchor="w", padx=20, pady=(10,0))
        ent_key = ctk.CTkEntry(d)
        ent_key.pack(fill="x", padx=20, pady=5)
        if edit_key: ent_key.insert(0, edit_key)

        ctk.CTkLabel(d, text="Typ Snippetu:", text_color=colors.get("text_color")).pack(anchor="w", padx=20, pady=(10,0))
        combo_type = ctk.CTkComboBox(d, values=["text", "app", "macro"])
        combo_type.set(edit_type)
        combo_type.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(d, text="Skrót klawiszowy:", text_color=colors.get("text_color")).pack(anchor="w", padx=20, pady=(10,0))

        # Click-to-bind for snippets too!
        self.snippet_hk_var = tk.StringVar(value=edit_hotkey)

        def capture_snip_hk():
            btn_hk.configure(text="Naciśnij klawisz...", fg_color="red")
            d.update()
            try:
                hk = keyboard.read_hotkey(suppress=False)
                self.snippet_hk_var.set(hk)
                btn_hk.configure(text=hk, fg_color="#555")
            except:
                btn_hk.configure(text="Błąd", fg_color="#555")

        btn_hk = ctk.CTkButton(d, textvariable=self.snippet_hk_var, command=capture_snip_hk, fg_color="#555")
        btn_hk.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(d, text="Treść / Ścieżka / Makro:", text_color=colors.get("text_color")).pack(anchor="w", padx=20, pady=(10,0))
        txt_content = ctk.CTkTextbox(d, height=120)
        txt_content.pack(fill="both", expand=True, padx=20, pady=5)
        if edit_content: txt_content.insert("0.0", edit_content)

        def save():
            k = ent_key.get().strip()
            hk = self.snippet_hk_var.get().strip().lower()
            c = txt_content.get("0.0", "end").strip()
            t = combo_type.get()

            if k and c:
                if edit_key and edit_key != k:
                    cfg.snippets.remove_snippet(edit_key)

                cfg.snippets.add_snippet(k, c, type=t, hotkey=hk)
                self.refresh_snip()
                d.destroy()

        ctk.CTkButton(d, text="Zapisz", command=save, fg_color=colors.get("button_color"), text_color="black", height=40).pack(fill="x", padx=20, pady=20)

    # --- HISTORY ---
    def setup_hist(self):
        self.hist_scroll = ctk.CTkScrollableFrame(self.tabs["Hist"])
        self.hist_scroll.pack(fill="both", expand=True)
        self.refresh_hist()

    def refresh_hist(self):
        for w in self.hist_scroll.winfo_children(): w.destroy()
        for entry in cfg.history:
            HistoryItem(self.hist_scroll, entry).pack(fill="x", pady=2)

    # --- SETTINGS ---
    def setup_sett(self):
        f = ctk.CTkScrollableFrame(self.tabs["Sett"])
        f.pack(fill="both", expand=True, padx=5, pady=5)

        colors = cfg.get_theme_colors()

        # --- API Section ---
        ctk.CTkLabel(f, text="API & Model", font=("Arial", 14, "bold"), text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(10,5))

        ctk.CTkLabel(f, text="Klucz API (Groq):", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.ent_api = ctk.CTkEntry(f, width=400)
        self.ent_api.pack(anchor="w", padx=20, pady=5)
        self.ent_api.insert(0, cfg.config["api_key"])

        ctk.CTkLabel(f, text="Model AI:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        models = cfg.config.get("models_list", ["llama-3.3-70b-versatile"])
        self.combo_model = ctk.CTkComboBox(f, values=models, width=300)
        self.combo_model.set(cfg.config.get("model", models[0]))
        self.combo_model.pack(anchor="w", padx=20, pady=5)

        # --- Appearance ---
        ctk.CTkLabel(f, text="Wygląd", font=("Arial", 14, "bold"), text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(20,5))

        ctk.CTkLabel(f, text="Motyw:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.combo_theme = ctk.CTkComboBox(f, values=["Dark", "Light", "Creamy", "High Visibility"], width=300, command=self.change_theme_live)
        self.combo_theme.set(cfg.config.get("theme", "Dark"))
        self.combo_theme.pack(anchor="w", padx=20, pady=5)

        ctk.CTkLabel(f, text="Czcionka interfejsu:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.combo_font = ctk.CTkComboBox(f, values=FONTS, width=300, command=self.change_font_live)
        self.combo_font.set(cfg.config["font_family"])
        self.combo_font.pack(anchor="w", padx=20, pady=5)

        # --- Hotkeys (Click-to-bind) ---
        ctk.CTkLabel(f, text="Skróty Klawiszowe (Kliknij by zmienić)", font=("Arial", 14, "bold"), text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(20,5))

        self.hotkey_vars = {}
        hotkey_map = {
            "Korekta": "hotkey_correct",
            "Tłumaczenie": "hotkey_translate",
            "Streszczenie": "hotkey_summarize",
            "Zmiana Tonu": "hotkey_tone",
            "Wyjaśnienie": "hotkey_explain"
        }

        for label, key in hotkey_map.items():
            fr = ctk.CTkFrame(f, fg_color="transparent")
            fr.pack(fill="x", padx=20, pady=2)
            ctk.CTkLabel(fr, text=label, width=120, anchor="w", text_color=colors.get("text_color")).pack(side="left")

            curr_val = cfg.config.get(key, "Brak")
            self.hotkey_vars[key] = tk.StringVar(value=curr_val)

            # Button for binding
            btn = ctk.CTkButton(fr, textvariable=self.hotkey_vars[key], width=200,
                                fg_color=colors.get("input_bg"), hover_color=colors.get("frame_color"))

            # Capture logic with closure
            def start_bind(k=key, b=btn):
                self.hotkey_vars[k].set("Naciśnij klawisz...")
                b.configure(fg_color="red")
                self.update() # Force redraw

                try:
                    hk = keyboard.read_hotkey(suppress=False)
                    self.hotkey_vars[k].set(hk)
                    # Update config immediately
                    cfg.config[k] = hk
                    cfg.save_config()
                    self.register_hotkeys()
                    b.configure(fg_color=colors.get("input_bg"))
                except Exception as e:
                    self.hotkey_vars[k].set("Błąd")
                    print(e)

            btn.configure(command=start_bind)
            btn.pack(side="left", padx=10)

        # --- Prompts ---
        ctk.CTkLabel(f, text="Prompts Systemowe", font=("Arial", 14, "bold"), text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(20,5))

        self.prompts_entries = {}
        prompts = cfg.config.get("prompts", {})

        for key, val in prompts.items():
            ctk.CTkLabel(f, text=f"Prompt: {key}", text_color=colors.get("text_color")).pack(anchor="w", padx=20, pady=(5,0))
            txt = ctk.CTkTextbox(f, height=60, width=500)
            txt.pack(anchor="w", padx=20, pady=2)
            txt.insert("0.0", val)
            self.prompts_entries[key] = txt

        # --- Buttons ---
        b_frame = ctk.CTkFrame(f, fg_color="transparent")
        b_frame.pack(fill="x", padx=10, pady=30)

        ctk.CTkButton(b_frame, text="Zapisz pozostałe", command=self.save_sett, fg_color="#2CC985", text_color="black").pack(side="left", padx=10)
        ctk.CTkButton(b_frame, text="Restart Aplikacji", command=self.restart_app, fg_color="#FF4747").pack(side="left", padx=10)

    def change_theme_live(self, choice):
        cfg.config["theme"] = choice
        self.update_theme()
        # Full refresh might be needed for some colors, but let's try basic
        self.refresh_dash()

    def change_font_live(self, choice):
        cfg.config["font_family"] = choice
        self.ask_restart("Zmiana czcionki wymaga restartu. Czy zrestartować teraz?")

    def ask_restart(self, msg):
        import tkinter.messagebox
        if tkinter.messagebox.askyesno("Restart", msg):
            self.restart_app()

    def update_theme(self):
        t = cfg.config.get("theme", "Dark")
        if t == "Light": ctk.set_appearance_mode("Light")
        else: ctk.set_appearance_mode("Dark")

        # Apply colors to window
        colors = cfg.get_theme_colors()
        self.configure(fg_color=colors.get("fg_color"))

    def save_sett(self):
        cfg.config["api_key"] = self.ent_api.get()
        cfg.config["model"] = self.combo_model.get()
        cfg.config["font_family"] = self.combo_font.get()
        cfg.config["theme"] = self.combo_theme.get()

        # Save prompts
        new_prompts = {}
        for key, widget in self.prompts_entries.items():
            new_prompts[key] = widget.get("0.0", "end").strip()
        cfg.config["prompts"] = new_prompts

        cfg.save_config()
        ai.configure()
        self.status.configure(text="Zapisano pomyślnie!", text_color="green")

    def restart_app(self):
        import sys
        import os
        self.quit_app()
        # Wait a bit to ensure tray icon is removed
        time.sleep(0.5)
        os.execl(sys.executable, sys.executable, *sys.argv)

    # --- DASHBOARD ---
    def setup_dash(self):
        f = self.tabs["Dash"]
        f.grid_columnconfigure((0,1,2), weight=1) # 3 columns for stats

        colors = cfg.get_theme_colors()
        font_large = (cfg.config["font_family"], colors.get("font_size_large", 18))

        # Stats Row
        self.c1 = self._stat_card(f, "Korekty", 0, 0, 0)
        self.c2 = self._stat_card(f, "Tłumaczenia", 0, 0, 1)

        # Words Card with Review Button
        fr = ctk.CTkFrame(f, fg_color=colors.get("frame_color", "#333"), border_width=2, border_color=colors.get("button_color"))
        fr.grid(row=0, column=2, padx=10, pady=10, sticky="ew")
        ctk.CTkLabel(fr, text="Słowa", text_color=colors.get("text_color")).pack(pady=5)
        self.c3_val = ctk.CTkLabel(fr, text="0", font=("Arial", 26, "bold"), text_color=colors.get("accent_text"))
        self.c3_val.pack(pady=2)
        ctk.CTkButton(fr, text="⚡ Przegląd", height=20, width=80, fg_color=colors.get("button_color"), text_color="black", command=self.open_review_mode).pack(pady=5)

        # Test Zone (Moved here)
        self.setup_test_zone(f, row=1)

        self.refresh_dash()

    def _stat_card(self, p, t, v, r, c):
        colors = cfg.get_theme_colors()
        fr = ctk.CTkFrame(p, fg_color=colors.get("frame_color", "#333"))
        fr.grid(row=r, column=c, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(fr, text=t, text_color=colors.get("text_color")).pack(pady=5)
        l = ctk.CTkLabel(fr, text=str(v), font=("Arial", 26, "bold"), text_color=colors.get("accent_text"))
        l.pack(pady=5)
        return l

    def refresh_dash(self):
        self.c1.configure(text=str(cfg.stats["corrected"]))
        self.c2.configure(text=str(cfg.stats["translated"]))
        self.c3_val.configure(text=str(cfg.stats.get("words_corrected", 0)))

    def open_review_mode(self):
        to_review = []
        seen = set()

        for entry in cfg.history:
            if entry.get("diffs"):
                for d in entry["diffs"]:
                    old = d["old"]
                    new = d["new"]
                    if old in cfg.auto_replace.replacements: continue
                    if old in cfg.auto_replace.ignored: continue

                    pair = (old, new)
                    if pair not in seen:
                        seen.add(pair)
                        to_review.append(pair)

        if not to_review:
            self.status.configure(text="Brak słówek do przeglądu!", text_color="yellow")
            return

        from corr_gui import QuickReviewDialog
        QuickReviewDialog(self, to_review)

    # --- SYSTEM ---
    def register_hotkeys(self):
        try: keyboard.unhook_all_hotkeys()
        except: pass

        actions = [
            ("hotkey_correct", "CORRECT"),
            ("hotkey_translate", "TRANSLATE"),
            ("hotkey_summarize", "SUMMARIZE"),
            ("hotkey_tone", "TONE_CHANGE"),
            ("hotkey_explain", "EXPLAIN")
        ]

        try:
            for cfg_key, action in actions:
                hk = cfg.config.get(cfg_key)
                if hk and hk != "Brak":
                    keyboard.add_hotkey(hk, lambda a=action: worker.trigger(a))

            keyboard.add_hotkey("f1", self.show_window)
        except Exception as e:
            self.status.configure(text=f"Hotkey Error: {e}", text_color="red")

    def setup_tray(self):
        img = Image.new('RGB', (64, 64), (30, 30, 30))
        ImageDraw.Draw(img).ellipse((16, 16, 48, 48), fill="#2CC985")
        self.tray = pystray.Icon("AI", img, "AI Assistant", menu=pystray.Menu(
            pystray.MenuItem("Pokaż", self.show_window),
            pystray.MenuItem("Wyjdź", self.quit_app)))
        threading.Thread(target=self.tray.run, daemon=True).start()

    def hide_window(self): self.withdraw()
    def show_window(self): self.deiconify(); self.lift(); self.focus_force()
    def quit_app(self): self.tray.stop(); self.quit()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
