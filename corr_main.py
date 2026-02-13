import customtkinter as ctk
import tkinter as tk
import threading
import queue
import time
import difflib
import keyboard
import pystray
from PIL import Image, ImageDraw, ImageTk
import os
import webbrowser

from corr_config import cfg, gui_queue, FONTS
from corr_ai import ai
from corr_gui import BubbleButton, HistoryItem, ReviewPopup, QuickReviewDialog
from corr_worker import worker

# --- MAIN APP ---
class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Assistant Pro v0.2.1")
        self.geometry("1050x810")
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # ESC to close/hide
        self.bind("<Escape>", lambda e: self.hide_window())

        self.update_theme()

        # Menu Bar
        self.create_menu_bar()

        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Font for tabs needs to be set via font config in CTkTabview?
        # Actually standard CTkTabview doesn't easily expose tab font size.
        # But we can try to configure it.
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)

        # Configure Tab Font - Normal weight, not bold.
        # "W terminalu niech te poszczególne zakładki będą jako każdy inny baton. No i niech nie będą pogrubione..."
        try:
             self.tabview._segmented_button.configure(
                 font=ctk.CTkFont(family=cfg.config["font_family"], size=16, weight="normal"),
                 corner_radius=10, # More rounded
             )
             # Try to simulate "separate buttons" by adding spacing if possible,
             # but segmented button is a single widget. corner_radius helps it look less like a bar.
        except: pass

        self.tabs = {
            "Dash": self.tabview.add("Dashboard"),
            "Hist": self.tabview.add("Historia"),
            "Snip": self.tabview.add("Snippety"),
            "Short": self.tabview.add("Skróty"),
            "Suno": self.tabview.add("Suno"),
            "Sett": self.tabview.add("Ustawienia"),
            "Info": self.tabview.add("Info"),
        }

        # Init Modules - Pre-load all content
        self.setup_dash()
        self.setup_hist()
        self.setup_snip()
        self.setup_short()
        self.setup_suno()
        self.setup_sett()
        self.setup_info()

        # Force focus on input
        self.after(100, lambda: self.test_in.focus_set())

        # Footer
        ver = cfg.get_version()
        self.status = ctk.CTkLabel(self, text=f"Gotowy | {ver}", anchor="w", height=30, font=("Arial", 12))
        self.status.grid(row=1, column=0, sticky="ew", padx=10)

        if not cfg.config.get("api_key"):
            self.status.configure(text="⚠️ Skonfiguruj klucz API w ustawieniach!", text_color="#ffcc00")

        # Static Badge (No Login Logic)
        self.show_user_badge()

        # Background tasks
        self.check_queue()
        self.register_hotkeys()
        self.setup_tray()

    def create_menu_bar(self):
        menubar = tk.Menu(self)

        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Zamknij do traya", command=self.hide_window)
        file_menu.add_command(label="Wyjdź", command=self.quit_app)
        menubar.add_cascade(label="Plik", menu=file_menu)

        # Edit
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Wyczyść historię", command=self.clear_history)
        menubar.add_cascade(label="Edycja", menu=edit_menu)

        # Settings link
        sett_menu = tk.Menu(menubar, tearoff=0)
        sett_menu.add_command(label="Otwórz ustawienia", command=lambda: self.tabview.set("Ustawienia"))
        menubar.add_cascade(label="Ustawienia", menu=sett_menu)

        self.config(menu=menubar)

    def clear_history(self):
        cfg.history = []
        cfg.save_history()
        self.refresh_hist()
        self.status.configure(text="Historia wyczyszczona.", text_color="green")

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
                elif msg == "INPUT":
                    # data = {"title": "...", "prompt": "...", "event": evt, "result": res}
                    d = ctk.CTkInputDialog(text=data['prompt'], title=data['title'])
                    res_val = d.get_input()
                    if res_val is not None:
                        data['result'].append(res_val)
                    data['event'].set()
        except queue.Empty: pass
        finally: self.after(200, self.check_queue)

    # --- DASHBOARD ---
    def setup_dash(self):
        f = self.tabs["Dash"]
        # Reset grid
        for w in f.winfo_children(): w.destroy()

        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(2, weight=1) # Output expands

        colors = cfg.get_theme_colors()
        font_base = (cfg.config["font_family"], colors.get("font_size_base", 14))
        font_large = (cfg.config["font_family"], colors.get("font_size_large", 18))
        font_lato = ("Lato", 20, "bold") # Hardcoded Lato as requested, or fallback if system matches

        # 1. Review Button (Top, Centered, Large, Shadow)
        top_frame = ctk.CTkFrame(f, fg_color="transparent")
        top_frame.grid(row=0, column=0, pady=(10, 5))

        # Yellow Frame + "Shell32" style icon (Folder/Search)
        btn_rev = ctk.CTkButton(top_frame, text="📂 PRZEGLĄD SŁÓW", width=300, height=50,
                                font=("Arial", 18, "bold"),
                                fg_color="#F1C40F", # Yellow
                                hover_color="#D4AC0D",
                                text_color="black",
                                command=self.open_review_mode)
        btn_rev.pack()

        # 2. Input Textbox (Centered, Narrower, Taller)
        input_container = ctk.CTkFrame(f, fg_color="transparent")
        input_container.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        input_container.grid_columnconfigure(0, weight=1)

        self.test_in = ctk.CTkTextbox(input_container, width=800, height=160, font=font_large,
                                      fg_color=colors.get("input_bg"), text_color=colors.get("text_color"))
        # Thick cursor
        self.test_in.configure(insertwidth=5)
        self.test_in.grid(row=0, column=0, pady=5)

        # Focus input by default
        self.after(500, lambda: self.test_in.focus_set())

        # 3. Paste Buttons
        action_area = ctk.CTkFrame(f, fg_color="transparent")
        action_area.grid(row=3, column=0, pady=10)

        # Paste Row
        paste_frame = ctk.CTkFrame(action_area, fg_color="transparent")
        paste_frame.pack(pady=10)

        # Smaller, light gray buttons
        paste_bg = "#d0d0d0" if colors.get("theme") != "Dark" else "#404040"

        btn_paste = ctk.CTkButton(paste_frame, text="WKLEJ TEKST", width=160, height=40,
                                  font=("Arial", 14), fg_color=paste_bg, text_color="black" if colors.get("theme")!="Dark" else "white",
                                  command=lambda: self.paste_to_input())
        btn_paste.pack(side="left", padx=40)

        btn_hist = ctk.CTkButton(paste_frame, text="HISTORIA (Win+V)", width=160, height=40,
                                 font=("Arial", 14), fg_color=paste_bg, text_color="black" if colors.get("theme")!="Dark" else "white",
                                 command=self.trigger_win_v)
        btn_hist.pack(side="left", padx=40)

        # 4. Action Buttons (2 Rows, Lato, Large)
        act_frame = ctk.CTkFrame(action_area, fg_color="transparent")
        act_frame.pack(pady=10)

        def mk_btn(parent, txt, code, shortcut_hint=""):
            # Frame as Button wrapper to support two font sizes
            btn_frame = ctk.CTkFrame(parent, width=220, height=55, fg_color=colors.get("button_color"), corner_radius=6)
            # Prevent shrinking
            btn_frame.pack_propagate(False)

            # Inner Labels
            l_main = ctk.CTkLabel(btn_frame, text=txt, font=font_lato, text_color="black")
            l_main.pack(pady=(5,0))

            if shortcut_hint:
                l_sub = ctk.CTkLabel(btn_frame, text=shortcut_hint, font=("Arial", 10), text_color="#333333")
                l_sub.pack(pady=(0,2))

            # Click bindings
            def on_click(e): self.run_dashboard_action(code)
            def on_right(e): self.show_disable_menu(e, code)

            for w in [btn_frame, l_main] + ([l_sub] if shortcut_hint else []):
                w.bind("<Button-1>", on_click)
                w.bind("<Button-3>", on_right)
                # Hover effect simulation (simple)
                w.bind("<Enter>", lambda e, f=btn_frame: f.configure(fg_color=colors.get("button_hover")))
                w.bind("<Leave>", lambda e, f=btn_frame: f.configure(fg_color=colors.get("button_color")))

            return btn_frame

        r1 = ctk.CTkFrame(act_frame, fg_color="transparent")
        r1.pack(pady=5)
        mk_btn(r1, "KOREKTA", "CORRECT", cfg.config.get("hotkey_correct", "")).pack(side="left", padx=10)
        mk_btn(r1, "TŁUMACZ", "TRANSLATE", cfg.config.get("hotkey_translate", "")).pack(side="left", padx=10)

        r2 = ctk.CTkFrame(act_frame, fg_color="transparent")
        r2.pack(pady=5)
        mk_btn(r2, "STRESZCZENIE", "SUMMARIZE", cfg.config.get("hotkey_summarize", "")).pack(side="left", padx=10)
        mk_btn(r2, "ZMIANA TONU", "TONE_CHANGE", cfg.config.get("hotkey_tone", "")).pack(side="left", padx=10)
        mk_btn(r2, "WYJAŚNIENIE", "EXPLAIN", cfg.config.get("hotkey_explain", "")).pack(side="left", padx=10)

        # 5. Output Area
        self.out_frame = ctk.CTkFrame(f, fg_color=colors.get("history_bg"))
        self.out_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=5)

        self.out_text = tk.Text(self.out_frame, bg=colors.get("history_bg"), fg=colors.get("text_color"),
                                font=font_large,
                                relief="flat", wrap="word", padx=10, pady=10,
                                insertwidth=5) # Thick cursor
        self.out_text.pack(fill="both", expand=True)

        # 6. Bottom Actions
        bot_frame = ctk.CTkFrame(f, fg_color="transparent")
        bot_frame.grid(row=5, column=0, pady=10)

        ctk.CTkButton(bot_frame, text="ZAAKCEPTUJ WSZYSTKO", width=200, height=40, fg_color="#2CC985", text_color="black",
                      command=self.accept_all_bubbles).pack(side="left", padx=10)

        ctk.CTkButton(bot_frame, text="RESETUJ", width=150, height=40, fg_color="#FF4747", text_color="white",
                      command=self.reset_output).pack(side="left", padx=10)

        # Context Menu for Disable
        self.disable_menu = tk.Menu(self, tearoff=0)

        # Context Menu for Textbox
        self.menu = tk.Menu(self, tearoff=0, bg=colors.get("frame_color"), fg=colors.get("text_color"))

    def show_disable_menu(self, event, action_code):
        self.disable_menu.delete(0, "end")

        self.disable_menu.add_command(label="Wyłącz", command=lambda: self.disable_func(action_code, -1))
        self.disable_menu.add_command(label="Wyłącz na 6 godzin", command=lambda: self.disable_func(action_code, 6))
        self.disable_menu.add_command(label="Wyłącz na 12 godzin", command=lambda: self.disable_func(action_code, 12))
        self.disable_menu.add_command(label="Wyłącz do ponownego uruchomienia", command=lambda: self.disable_func(action_code, None))

        self.disable_menu.tk_popup(event.x_root, event.y_root)

    def disable_func(self, code, hours):
        cfg.disable_function(code, hours)
        self.status.configure(text=f"Funkcja {code} została wyłączona.", text_color="yellow")

    def paste_to_input(self):
        try:
            txt = pyperclip.paste()
            self.test_in.insert("end", txt)
        except: pass

    def trigger_win_v(self):
        keyboard.send('windows+v')

    def copy_to_clipboard(self, widget):
        try:
            txt = widget.get("0.0", "end").strip()
            pyperclip.copy(txt)
            self.status.configure(text="Skopiowano do schowka!", text_color="green")
        except: pass

    def show_user_badge(self):
        colors = cfg.get_theme_colors()
        name = "Kamil Kowalczyk" # Hardcoded as requested
        # Larger Avatar (48px height approx via font + padding)
        # Position: "ciutkę do góry i ciutkę w prawo"
        # Prev: relx=0.98, rely=0.02.
        # New: relx=0.99, rely=0.01 (Higher and more right)
        badge = ctk.CTkLabel(self.tabs["Dash"], text=f"👤 {name}",
                             font=("Arial", 20, "bold"),
                             height=48,
                             text_color=colors.get("text_color"),
                             fg_color=colors.get("frame_color"),
                             corner_radius=24) # Rounded pill
        badge.place(relx=0.99, rely=0.01, anchor="ne")

    def run_dashboard_action(self, action_code):
        # Check if enabled
        if not cfg.is_function_enabled(action_code):
            self.status.configure(text=f"Funkcja {action_code} jest wyłączona.", text_color="red")
            return

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

    def accept_all_bubbles(self):
        for child in self.out_text.winfo_children():
            if isinstance(child, BubbleButton):
                if child.cget("fg_color") != "transparent":
                     self.resolve_bubble(child, child.cget("text"))
        self.status.configure(text="Zaakceptowano wszystkie zmiany.", text_color="green")

    def reset_output(self):
        self.out_text.delete("1.0", "end")
        self.test_in.delete("1.0", "end")

    # --- SHORTCUTS ---
    def setup_short(self):
        f = self.tabs["Short"]
        for w in f.winfo_children(): w.destroy()

        colors = cfg.get_theme_colors()

        ctk.CTkLabel(f, text="Skróty (Visual Reference)", font=("Arial", 16, "bold"), text_color=colors.get("text_color")).pack(pady=10)

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

        target_dir = r"C:\Users\kamil\Pictures\Screenshots\Shortcuts"
        if not os.path.exists(target_dir):
             typo = r"C:\Users\kamil\Pictures\Screenshots\Shortuts"
             if os.path.exists(typo): target_dir = typo

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
        else:
             ctk.CTkLabel(scroll, text=f"Brak katalogu:\n{target_dir}", text_color="gray").pack(pady=20)

    # --- SNIPPETS & ICONS ---
    def setup_snip(self):
        f = self.tabs["Snip"]
        for w in f.winfo_children(): w.destroy()

        colors = cfg.get_theme_colors()

        # Tools
        tool_bar = ctk.CTkFrame(f, fg_color="transparent")
        tool_bar.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(tool_bar, text="➕ Nowy Snippet", command=self.add_snippet_dialog,
                      fg_color=colors.get("button_color"), text_color="black").pack(side="left")

        # Search Bar
        self.snip_search_var = tk.StringVar()
        self.snip_search_var.trace("w", lambda *args: self.refresh_snip())
        entry_search = ctk.CTkEntry(tool_bar, placeholder_text="Szukaj snippetu...", textvariable=self.snip_search_var, width=250)
        entry_search.pack(side="left", padx=20)

        ctk.CTkLabel(tool_bar, text="Wpisz skrót (np. ;mail) -> Spacja", text_color="gray").pack(side="right")

        # List
        self.snip_scroll = ctk.CTkScrollableFrame(f)
        self.snip_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.refresh_snip()

    def refresh_snip(self):
        for w in self.snip_scroll.winfo_children(): w.destroy()
        colors = cfg.get_theme_colors()
        search_q = self.snip_search_var.get().lower()

        for key, data in cfg.snippets.snippets.items():
            # Search Filter
            content_txt = data['content'].lower()
            hk_txt = (data.get("hotkey") or "").lower()
            if search_q:
                if (search_q not in key.lower()) and (search_q not in content_txt) and (search_q not in hk_txt):
                    continue

            fr = ctk.CTkFrame(self.snip_scroll, fg_color=colors.get("history_bg"))
            fr.pack(fill="x", pady=2, padx=5)

            t = data.get("type", "text")
            icon = "📝" if t == "text" else ("🚀" if t == "app" else "🤖")

            # Larger Icon (32px font approx)
            ctk.CTkLabel(fr, text=icon, font=("Arial", 32), width=50).pack(side="left", padx=5)

            # Key
            ctk.CTkLabel(fr, text=key, font=("Consolas", 16, "bold"), text_color=colors.get("accent_text"), width=100, anchor="w").pack(side="left", padx=5)

            content_prev = data['content'][:40] + "..." if len(data['content']) > 40 else data['content']
            ctk.CTkLabel(fr, text=content_prev, text_color=colors.get("text_color"), anchor="w").pack(side="left", fill="x", expand=True)

            hk = data.get("hotkey")
            if hk:
                ctk.CTkLabel(fr, text=f"[{hk}]", text_color="gray", font=("Consolas", 11)).pack(side="left", padx=10)

            # Larger Buttons (48x48 requested)
            ctk.CTkButton(fr, text="🗑️", width=50, height=50, font=("Arial", 20), fg_color="transparent", text_color="red", hover_color=colors.get("frame_color"),
                          command=lambda k=key: self.delete_snippet(k)).pack(side="right", padx=5)
            ctk.CTkButton(fr, text="✏️", width=50, height=50, font=("Arial", 20), fg_color="transparent", text_color=colors.get("text_color"), hover_color=colors.get("frame_color"),
                          command=lambda k=key: self.edit_snippet(k)).pack(side="right", padx=5)

    def add_snippet_dialog(self):
        self._snippet_dialog()

    def edit_snippet(self, key):
        data = cfg.snippets.snippets[key]
        self._snippet_dialog(key, data['content'], data.get('type', 'text'), data.get('hotkey', ''), data.get('schedule'))

    def delete_snippet(self, key):
        cfg.snippets.remove_snippet(key)
        self.refresh_snip()
        self.status.configure(text=f"Usunięto snippet: {key}", text_color="red")

    def _snippet_dialog(self, edit_key=None, edit_content=None, edit_type="text", edit_hotkey="", edit_schedule=None):
        d = ctk.CTkToplevel(self)
        d.title("Edytor Snippetu")
        d.geometry("500x750")
        d.attributes("-topmost", True)
        d.grab_set() # Modal - block interaction with main window
        d.focus_force()

        # Bind ESC to close snippet dialog too
        d.bind("<Escape>", lambda e: d.destroy())

        colors = cfg.get_theme_colors()
        d.configure(fg_color=colors.get("fg_color"))

        # Scrollable container for dialog content
        scroll = ctk.CTkScrollableFrame(d, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(scroll, text="Skrót tekstowy (np. ;tel):", text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(10,0))
        ent_key = ctk.CTkEntry(scroll)
        ent_key.pack(fill="x", padx=10, pady=5)
        if edit_key: ent_key.insert(0, edit_key)

        ctk.CTkLabel(scroll, text="Typ Snippetu:", text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(10,0))
        combo_type = ctk.CTkComboBox(scroll, values=["text", "app", "macro"])
        combo_type.set(edit_type)
        combo_type.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(scroll, text="Skrót klawiszowy:", text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(10,0))

        self.snippet_hk_var = tk.StringVar(value=edit_hotkey)

        def capture_snip_hk():
            # Light Beige background for recording (#F5F5DC or similar)
            btn_hk.configure(text="Naciśnij klawisz...", fg_color="#E0E0C0", text_color="black")
            d.update()
            try:
                hk = keyboard.read_hotkey(suppress=False)
                # FORMAT UPPERCASE
                hk = hk.upper().replace("+", " + ")
                self.snippet_hk_var.set(hk)
                btn_hk.configure(text=hk, fg_color="#555", text_color="white")
            except:
                btn_hk.configure(text="Błąd", fg_color="#555", text_color="white")

        btn_hk = ctk.CTkButton(scroll, textvariable=self.snippet_hk_var, command=capture_snip_hk, fg_color="#555")
        btn_hk.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(scroll, text="Treść / Ścieżka / Makro:", text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(10,0))
        txt_content = ctk.CTkTextbox(scroll, height=100)
        txt_content.configure(insertwidth=5) # Thick cursor
        txt_content.pack(fill="x", padx=10, pady=5)
        if edit_content: txt_content.insert("0.0", edit_content)

        # --- SCHEDULING UI ---
        ctk.CTkLabel(scroll, text="Harmonogram (Opcjonalny):", font=("Arial", 12, "bold"), text_color=colors.get("accent_text")).pack(anchor="w", padx=10, pady=(20,5))
        ctk.CTkLabel(scroll, text="Snippet zadziała tylko w podanych godzinach i dniach.", font=("Arial", 10), text_color="gray").pack(anchor="w", padx=10)

        sch_frame = ctk.CTkFrame(scroll, fg_color=colors.get("frame_color"))
        sch_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(sch_frame, text="Godziny (HH:MM):", text_color="gray").pack(pady=5)
        time_row = ctk.CTkFrame(sch_frame, fg_color="transparent")
        time_row.pack()

        ent_start = ctk.CTkEntry(time_row, width=80, placeholder_text="08:00")
        ent_start.pack(side="left", padx=5)
        ctk.CTkLabel(time_row, text="-", text_color="gray").pack(side="left")
        ent_end = ctk.CTkEntry(time_row, width=80, placeholder_text="16:00")
        ent_end.pack(side="left", padx=5)

        ctk.CTkLabel(sch_frame, text="Dni tygodnia:", text_color="gray").pack(pady=(10,5))
        days_row = ctk.CTkFrame(sch_frame, fg_color="transparent")
        days_row.pack(pady=5)

        day_vars = []
        days_labels = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]
        for i, lbl in enumerate(days_labels):
            v = ctk.BooleanVar(value=True) # Default all checked
            chk = ctk.CTkCheckBox(days_row, text=lbl, variable=v, width=40, font=("Arial", 10))
            chk.pack(side="left", padx=2)
            day_vars.append(v)

        # Load existing schedule
        if edit_schedule:
            ent_start.insert(0, edit_schedule.get("start", ""))
            ent_end.insert(0, edit_schedule.get("end", ""))
            if "days" in edit_schedule:
                for i, v in enumerate(day_vars):
                    v.set(i in edit_schedule["days"])

        def save():
            k = ent_key.get().strip()
            hk = self.snippet_hk_var.get().strip()
            c = txt_content.get("0.0", "end").strip()
            t = combo_type.get()

            # Schedule Parse
            sch = None
            s_t = ent_start.get().strip()
            e_t = ent_end.get().strip()
            sel_days = [i for i, v in enumerate(day_vars) if v.get()]

            if s_t or e_t or len(sel_days) < 7:
                sch = {
                    "start": s_t if s_t else "00:00",
                    "end": e_t if e_t else "23:59",
                    "days": sel_days
                }

            if k and c:
                if edit_key and edit_key != k:
                    cfg.snippets.remove_snippet(edit_key)

                cfg.snippets.add_snippet(k, c, type=t, hotkey=hk, schedule=sch)
                self.refresh_snip()
                d.destroy()

        ctk.CTkButton(scroll, text="Zapisz", command=save, fg_color=colors.get("button_color"), text_color="black", height=40).pack(fill="x", padx=10, pady=20)

    # --- INFO ---
    def setup_info(self):
        f = self.tabs["Info"]
        for w in f.winfo_children(): w.destroy()

        colors = cfg.get_theme_colors()

        # Logo
        logo_path = r"D:\exis\Icons\neue 3xxx\if_WoodMannequin_by_Artdesigner_60883.png"
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path)
                img = img.resize((150, 150))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(150, 150))
                ctk.CTkLabel(f, image=ctk_img, text="").pack(pady=20)
            except: pass

        ctk.CTkLabel(f, text="AI Assistant Pro v0.2.1", font=("Arial", 24, "bold"), text_color=colors.get("accent_text")).pack(pady=10)
        ctk.CTkLabel(f, text="Aplikacja stworzona do automatyzacji, korekty tekstu i zarządzania snippetami.", text_color=colors.get("text_color")).pack()
        ctk.CTkLabel(f, text="Kamil Kowalczyk © 2024", text_color="gray").pack(pady=5)

        ctk.CTkLabel(f, text="Plany na przyszłość:", font=("Arial", 16, "bold"), text_color=colors.get("text_color")).pack(pady=(30,10))
        plans = [
            "- Integracja z Suno API (Auto-Music)",
            "- Zaawansowane makra głosowe",
            "- Synchronizacja chmurowa"
        ]
        for p in plans:
            ctk.CTkLabel(f, text=p, text_color="gray").pack()

    # --- SUNO ---
    def setup_suno(self):
        f = self.tabs["Suno"]
        for w in f.winfo_children(): w.destroy()

        colors = cfg.get_theme_colors()

        ctk.CTkLabel(f, text="Suno Automation", font=("Arial", 24, "bold"), text_color=colors.get("accent_text")).pack(pady=10)

        ctk.CTkButton(f, text="Otwórz suno.com/create", command=lambda: webbrowser.open("https://suno.com/create"),
                      width=200, height=40, fg_color=colors.get("button_color"), text_color="black").pack(pady=10)

        # Custom Mode Fields
        ctk.CTkLabel(f, text="Lyrics:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.suno_lyrics = ctk.CTkTextbox(f, height=120)
        self.suno_lyrics.configure(insertwidth=5)
        self.suno_lyrics.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(f, text="Style of Music:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.suno_style = ctk.CTkEntry(f)
        self.suno_style.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(f, text="Title:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.suno_title = ctk.CTkEntry(f)
        self.suno_title.pack(fill="x", padx=20, pady=5)

        ctk.CTkButton(f, text="🚀 AUTO-FILL (Custom Mode)", command=self.run_suno_autofill,
                      width=250, height=50, fg_color="#F1C40F", text_color="black").pack(pady=20)

        ctk.CTkLabel(f, text="Instrukcja: Kliknij przycisk, strona się otworzy.\nMasz 5 sekund na kliknięcie w pole 'Lyrics' na stronie Suno.\nSkrypt wypełni resztę (używając Tab).", text_color="gray").pack(pady=10)

    def run_suno_autofill(self):
        l = self.suno_lyrics.get("0.0", "end").strip()
        s = self.suno_style.get().strip()
        t = self.suno_title.get().strip()

        webbrowser.open("https://suno.com/create")
        self.status.configure(text="⏳ Kliknij w pole LYRICS w ciągu 5 sekund...", text_color="yellow")

        def _fill():
            time.sleep(5)
            # Sequence: Type Lyrics -> TAB -> Type Style -> TAB -> Type Title
            if l:
                keyboard.write(l)
                time.sleep(0.5)

            # Navigate to Style
            keyboard.send("tab")
            time.sleep(0.5)

            if s:
                keyboard.write(s)
                time.sleep(0.5)

            # Navigate to Title
            keyboard.send("tab")
            time.sleep(0.5)

            if t:
                keyboard.write(t)

            gui_queue.put(("STATUS", {"text": "✅ Formularz wypełniony!", "color": "green"}))

        threading.Thread(target=_fill, daemon=True).start()

    # --- HISTORY ---
    def setup_hist(self):
        self.hist_scroll = ctk.CTkScrollableFrame(self.tabs["Hist"])
        self.hist_scroll.pack(fill="both", expand=True)
        self.refresh_hist()

    def refresh_hist(self):
        for w in self.hist_scroll.winfo_children(): w.destroy()
        for entry in cfg.history:
            HistoryItem(self.hist_scroll, entry).pack(fill="x", pady=2)

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
        QuickReviewDialog(self, to_review)

    # --- SETTINGS ---
    def setup_sett(self):
        f = ctk.CTkScrollableFrame(self.tabs["Sett"])
        f.pack(fill="both", expand=True, padx=5, pady=5)

        colors = cfg.get_theme_colors()

        # Appearance
        ctk.CTkLabel(f, text="Wygląd", font=("Arial", 14, "bold"), text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(20,5))

        ctk.CTkLabel(f, text="Motyw:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.combo_theme = ctk.CTkComboBox(f, values=["Dark", "Light", "Creamy", "High Visibility"], width=300, command=self.change_theme_live)
        self.combo_theme.set(cfg.config.get("theme", "Light"))
        self.combo_theme.pack(anchor="w", padx=20, pady=5)

        ctk.CTkLabel(f, text="Czcionka interfejsu:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.combo_font = ctk.CTkComboBox(f, values=FONTS, width=300, command=self.change_font_live)
        self.combo_font.set(cfg.config["font_family"])
        self.combo_font.pack(anchor="w", padx=20, pady=5)

        ctk.CTkLabel(f, text="Rozmiar czcionki:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.slider_font_size = ctk.CTkSlider(f, from_=10, to=30, number_of_steps=20, width=300, command=self.change_font_size_live)
        self.slider_font_size.set(cfg.config.get("font_size", 18))
        self.slider_font_size.pack(anchor="w", padx=20, pady=5)
        self.lbl_font_size = ctk.CTkLabel(f, text=f"{int(cfg.config.get('font_size', 18))} px", text_color="gray")
        self.lbl_font_size.pack(anchor="w", padx=20)

        # Hotkeys
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
            # Force Uppercase for display
            if curr_val: curr_val = curr_val.upper()
            self.hotkey_vars[key] = tk.StringVar(value=curr_val)

            btn = ctk.CTkButton(fr, textvariable=self.hotkey_vars[key], width=200,
                                fg_color=colors.get("input_bg"), hover_color=colors.get("frame_color"))

            def start_bind(k=key, b=btn):
                self.hotkey_vars[k].set("Naciśnij klawisz...")
                b.configure(fg_color="red")
                self.update()
                try:
                    hk = keyboard.read_hotkey(suppress=False)
                    # UPPERCASE FORMATTING
                    hk = hk.upper().replace("+", " + ")

                    # Safety Check
                    forbidden = ["CTRL", "SHIFT", "ALT", "WIN", "ESC", "ENTER", "SPACE", "BACKSPACE", "TAB"]
                    if hk in forbidden:
                         self.hotkey_vars[k].set("Błąd: Zły Klawisz")
                         b.configure(fg_color=colors.get("input_bg"))
                         self.status.configure(text=f"Nie można przypisać samego klawisza: {hk}", text_color="red")
                         return

                    self.hotkey_vars[k].set(hk)
                    cfg.config[k] = hk
                    cfg.save_config()
                    self.register_hotkeys()
                    b.configure(fg_color=colors.get("input_bg"))
                except Exception as e:
                    self.hotkey_vars[k].set("Błąd")

            btn.configure(command=start_bind)
            btn.pack(side="left", padx=10)

        # Prompts
        ctk.CTkLabel(f, text="Prompts Systemowe", font=("Arial", 14, "bold"), text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(20,5))
        self.prompts_entries = {}
        prompts = cfg.config.get("prompts", {})
        for key, val in prompts.items():
            ctk.CTkLabel(f, text=f"Prompt: {key}", text_color=colors.get("text_color")).pack(anchor="w", padx=20, pady=(5,0))
            txt = ctk.CTkTextbox(f, height=60, width=500)
            txt.pack(anchor="w", padx=20, pady=2)
            txt.insert("0.0", val)
            self.prompts_entries[key] = txt

        # Buttons
        b_frame = ctk.CTkFrame(f, fg_color="transparent")
        b_frame.pack(fill="x", padx=10, pady=30)
        ctk.CTkButton(b_frame, text="Zapisz ustawienia", command=self.save_sett, fg_color="#2CC985", text_color="black").pack(side="left", padx=10)
        ctk.CTkButton(b_frame, text="Restart Aplikacji", command=self.restart_app, fg_color="#FF4747").pack(side="left", padx=10)

        # API (Moved to Bottom)
        ctk.CTkLabel(f, text="API & Model", font=("Arial", 14, "bold"), text_color=colors.get("text_color")).pack(anchor="w", padx=10, pady=(30,5))

        ctk.CTkLabel(f, text="Klucz API (Groq):", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        self.ent_api = ctk.CTkEntry(f, width=400)
        self.ent_api.pack(anchor="w", padx=20, pady=5)
        self.ent_api.insert(0, cfg.config["api_key"])

        ctk.CTkLabel(f, text="Model AI:", text_color=colors.get("text_color")).pack(anchor="w", padx=20)
        models = cfg.config.get("models_list", ["llama-3.3-70b-versatile"])
        self.combo_model = ctk.CTkComboBox(f, values=models, width=300)
        self.combo_model.set(cfg.config.get("model", models[0]))
        self.combo_model.pack(anchor="w", padx=20, pady=5)

    def change_theme_live(self, choice):
        cfg.config["theme"] = choice
        self.update_theme()
        # Full rebuild might be needed for proper reload, but for now:
        self.setup_dash() # Rebuild dash
        self.setup_sett() # Rebuild settings to reflect color changes
        # Others won't change until clicked or rebuilt

    def change_font_live(self, choice):
        cfg.config["font_family"] = choice
        self.ask_restart("Zmiana czcionki wymaga restartu. Czy zrestartować teraz?")

    def change_font_size_live(self, val):
        size = int(val)
        self.lbl_font_size.configure(text=f"{size} px")
        cfg.config["font_size"] = size
        # We don't save immediately on slide to avoid disk spam, but save on 'Zapisz' button
        # However, user might expect immediate effect? Not easy without full reload.
        # Just update config in memory, save button will persist.

    def ask_restart(self, msg):
        import tkinter.messagebox
        if tkinter.messagebox.askyesno("Restart", msg):
            self.restart_app()

    def update_theme(self):
        t = cfg.config.get("theme", "Light")
        if t == "Light" or t == "Creamy": ctk.set_appearance_mode("Light")
        else: ctk.set_appearance_mode("Dark")
        colors = cfg.get_theme_colors()
        self.configure(fg_color=colors.get("fg_color"))

    def save_sett(self):
        cfg.config["api_key"] = self.ent_api.get()
        cfg.config["model"] = self.combo_model.get()
        cfg.config["font_family"] = self.combo_font.get()
        cfg.config["font_size"] = int(self.slider_font_size.get())
        cfg.config["theme"] = self.combo_theme.get()

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
        time.sleep(0.5)
        os.execl(sys.executable, sys.executable, *sys.argv)

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
                    # Remove spaces for binding logic, keep for display
                    hk_bind = hk.replace(" ", "")
                    keyboard.add_hotkey(hk_bind, lambda a=action: worker.trigger(a))

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
