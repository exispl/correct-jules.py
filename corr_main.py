import customtkinter as ctk
import tkinter as tk
import threading
import queue
import time
import difflib
import keyboard
import pystray
from PIL import Image, ImageDraw

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
            "Sett": self.tabview.add("Ustawienia"),
        }

        # Init Modules
        self.setup_dash()
        self.setup_hist()
        self.setup_sett()

        # Footer
        self.status = ctk.CTkLabel(self, text="Gotowy", anchor="w", height=25)
        self.status.grid(row=1, column=0, sticky="ew", padx=10)

        if not cfg.config.get("api_key"):
            self.status.configure(text="⚠️ Skonfiguruj klucz API w ustawieniach!", text_color="#ffcc00")

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

        # Container
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=10, pady=5)
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(2, weight=1) # Output expands

        # Input Area
        input_label_frame = ctk.CTkFrame(f, fg_color="transparent")
        input_label_frame.grid(row=0, column=0, sticky="ew", padx=5)

        ctk.CTkLabel(input_label_frame, text="Wprowadź tekst:", text_color=colors.get("text_color")).pack(side="left")

        # Tools Icons (Copy, Paste History)
        ctk.CTkButton(input_label_frame, text="📋", width=30, height=20, fg_color="transparent", hover_color=colors.get("frame_color"),
                      text_color=colors.get("text_color"), command=lambda: self.copy_to_clipboard(self.test_in)).pack(side="right", padx=2)

        ctk.CTkButton(input_label_frame, text="🗂️ Win+V", width=60, height=20, fg_color="transparent", hover_color=colors.get("frame_color"),
                      text_color=colors.get("text_color"), command=self.trigger_win_v).pack(side="right", padx=2)

        self.test_in = ctk.CTkTextbox(f, height=100, font=(cfg.config["font_family"], cfg.config["font_size"]),
                                      fg_color=colors.get("input_bg"), text_color=colors.get("text_color"))
        self.test_in.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

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
            ctk.CTkButton(btn_frame, text=label, width=120, fg_color=colors.get("button_color"),
                          hover_color=colors.get("button_hover"), text_color="white",
                          command=lambda c=code: self.run_dashboard_action(c)).pack(pady=2)

        # Output Area
        output_label_frame = ctk.CTkFrame(f, fg_color="transparent")
        output_label_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=(10,0))
        ctk.CTkLabel(output_label_frame, text="Wynik:", text_color=colors.get("text_color")).pack(side="left")

        ctk.CTkButton(output_label_frame, text="📋", width=30, height=20, fg_color="transparent", hover_color=colors.get("frame_color"),
                      text_color=colors.get("text_color"), command=lambda: self.copy_to_clipboard(self.out_text)).pack(side="right", padx=2)

        self.out_frame = ctk.CTkFrame(f, fg_color=colors.get("history_bg"))
        self.out_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)

        self.out_text = tk.Text(self.out_frame, bg=colors.get("history_bg"), fg=colors.get("text_color"),
                                font=(cfg.config["font_family"], cfg.config["font_size"]),
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
        keyboard.send('windows+v')
        self.status.configure(text="Otwarto historię schowka (Win+V)", text_color=colors.get("accent_text"))

    def run_dashboard_action(self, action_code):
        txt = self.test_in.get("0.0", "end").strip()
        if not txt: return
        self.status.configure(text=f"AI pracuje ({action_code})...", text_color="yellow")
        threading.Thread(target=self._thread_test, args=(txt, action_code), daemon=True).start()

    def _thread_test(self, txt, action_code):
        try:
            res, dur = ai.process_text(action_code, txt)
            if res:
                # If Correct or Tone Change, show bubbles
                if action_code in ["CORRECT", "TONE_CHANGE"]:
                    self.after(0, lambda: self.render_bubbles(txt, res, action_code))
                else:
                    # Just show text for Translate, Summarize, Explain
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

        # Tokenizacja słowna
        orig_words = original.split()
        res_words = result.split()
        matcher = difflib.SequenceMatcher(None, orig_words, res_words)

        diffs = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Tekst bez zmian
                segment = " ".join(res_words[j1:j2]) + " "
                self.out_text.insert("end", segment)
            elif tag in ('replace', 'insert'):
                # Zmiana -> Bubble
                new_phrase = " ".join(res_words[j1:j2])
                old_phrase = " ".join(orig_words[i1:i2])

                # Tworzymy BubbleButton
                btn = BubbleButton(self.out_text, text=new_phrase, original_text=old_phrase)
                # Bind events
                btn.bind("<Button-1>", lambda e, b=btn: self.show_bubble_menu(e, b))
                btn.bind("<Button-3>", lambda e, b=btn: self.show_bubble_menu(e, b))

                self.out_text.window_create("end", window=btn)
                self.out_text.insert("end", " ") # spacja po chmurce

                if old_phrase:
                    diffs.append({"old": old_phrase, "new": new_phrase})

        # Zapisz do historii
        cfg.add_history_entry(action_type, original, result, 0, diffs=diffs)

    def show_bubble_menu(self, event, btn):
        self.menu.delete(0, "end")

        new_text = btn.cget('text')
        old_text = btn.original_text

        # 1. Sugestia AI (Domyślna)
        self.menu.add_command(label=f"✅ Akceptuj: '{new_text}'",
                              command=lambda: self.resolve_bubble(btn, new_text))

        # 2. Auto-Replace
        if old_text:
             self.menu.add_command(label=f"⚡ Dodaj do Auto-Replace: '{old_text}' -> '{new_text}'",
                              command=lambda: self.add_to_autoreplace(btn, old_text, new_text))

        self.menu.add_separator()

        # 3. Przywróć oryginał (jeśli był)
        if old_text:
            self.menu.add_command(label=f"↩️ Przywróć: '{old_text}'",
                                  command=lambda: self.resolve_bubble(btn, old_text, is_revert=True))

            # 4. Ignoruj na zawsze
            self.menu.add_command(label=f"🚫 Ignoruj '{old_text}' (Nigdy nie zmieniaj)",
                                  command=lambda: self.ignore_word(btn, old_text))

        # 5. Edycja
        self.menu.add_separator()
        self.menu.add_command(label="✏️ Edytuj ręcznie...", command=lambda: self.manual_bubble_edit(btn))

        self.menu.tk_popup(event.x_root, event.y_root)

    def resolve_bubble(self, btn, text, is_revert=False):
        colors = cfg.get_theme_colors()
        txt_col = colors.get("text_color")

        if is_revert:
            btn.configure(text=text, fg_color="transparent", hover=False, text_color=txt_col)
        else:
            # Zatwierdzone
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
        # Scrollable frame for settings content
        f = ctk.CTkScrollableFrame(self.tabs["Sett"])
        f.pack(fill="both", expand=True, padx=5, pady=5)

        # --- API Section ---
        ctk.CTkLabel(f, text="API & Model", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(10,5))

        ctk.CTkLabel(f, text="Klucz API (Groq):").pack(anchor="w", padx=20)
        self.ent_api = ctk.CTkEntry(f, width=400)
        self.ent_api.pack(anchor="w", padx=20, pady=5)
        self.ent_api.insert(0, cfg.config["api_key"])

        ctk.CTkLabel(f, text="Model AI:").pack(anchor="w", padx=20)
        models = cfg.config.get("models_list", ["llama-3.3-70b-versatile"])
        self.combo_model = ctk.CTkComboBox(f, values=models, width=300)
        self.combo_model.set(cfg.config.get("model", models[0]))
        self.combo_model.pack(anchor="w", padx=20, pady=5)

        # --- Appearance ---
        ctk.CTkLabel(f, text="Wygląd", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(20,5))

        ctk.CTkLabel(f, text="Motyw:").pack(anchor="w", padx=20)
        self.combo_theme = ctk.CTkComboBox(f, values=["Dark", "Light", "Creamy"], width=300, command=self.change_theme_live)
        self.combo_theme.set(cfg.config.get("theme", "Dark"))
        self.combo_theme.pack(anchor="w", padx=20, pady=5)

        ctk.CTkLabel(f, text="Czcionka interfejsu:").pack(anchor="w", padx=20)
        self.combo_font = ctk.CTkComboBox(f, values=FONTS, width=300, command=self.change_font_live)
        self.combo_font.set(cfg.config["font_family"])
        self.combo_font.pack(anchor="w", padx=20, pady=5)

        # --- Hotkeys ---
        ctk.CTkLabel(f, text="Skróty Klawiszowe", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(20,5))

        self.hotkey_entries = {}
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
            ctk.CTkLabel(fr, text=label, width=120, anchor="w").pack(side="left")
            ent = ctk.CTkEntry(fr, width=200)
            ent.pack(side="left", padx=10)
            ent.insert(0, cfg.config.get(key, ""))
            self.hotkey_entries[key] = ent

        # --- Prompts ---
        ctk.CTkLabel(f, text="Prompty Systemowe", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(20,5))

        self.prompts_entries = {}
        prompts = cfg.config.get("prompts", {})

        for key, val in prompts.items():
            ctk.CTkLabel(f, text=f"Prompt: {key}").pack(anchor="w", padx=20, pady=(5,0))
            txt = ctk.CTkTextbox(f, height=60, width=500)
            txt.pack(anchor="w", padx=20, pady=2)
            txt.insert("0.0", val)
            self.prompts_entries[key] = txt

        # --- Buttons ---
        b_frame = ctk.CTkFrame(f, fg_color="transparent")
        b_frame.pack(fill="x", padx=10, pady=30)

        ctk.CTkButton(b_frame, text="Zapisz ustawienia", command=self.save_sett, fg_color="#2CC985", text_color="black").pack(side="left", padx=10)
        ctk.CTkButton(b_frame, text="Restart Aplikacji", command=self.restart_app, fg_color="#FF4747").pack(side="left", padx=10)

    def change_theme_live(self, choice):
        cfg.config["theme"] = choice
        self.update_theme()
        # Full refresh might be needed for some colors, but let's try basic
        self.refresh_dash()

    def change_font_live(self, choice):
        cfg.config["font_family"] = choice
        # Font changes usually require restart or traversing all widgets.
        # For simplicity, we just save config, but user might need restart for full effect.

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

        # Save Hotkeys with validation
        new_hotkeys = {}
        used_keys = set()

        for key, widget in self.hotkey_entries.items():
            hk = widget.get().strip().lower()
            if not hk: continue

            if hk in used_keys:
                self.status.configure(text=f"Błąd: Duplikat skrótu '{hk}'!", text_color="red")
                return

            try:
                keyboard.parse_hotkey(hk)
            except ValueError:
                self.status.configure(text=f"Błąd: Niepoprawny skrót '{hk}'!", text_color="red")
                return

            used_keys.add(hk)
            new_hotkeys[key] = hk

        for k, v in new_hotkeys.items():
            cfg.config[k] = v

        cfg.save_config()
        ai.configure()
        self.register_hotkeys() # Re-register immediately
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

        # Stats Row
        self.c1 = self._stat_card(f, "Korekty", 0, 0, 0)
        self.c2 = self._stat_card(f, "Tłumaczenia", 0, 0, 1)
        self.c3 = self._stat_card(f, "Słowa", 0, 0, 2)

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
        # Assuming we add word count later, placeholder for now
        self.c3.configure(text=str(cfg.stats.get("words_corrected", 0)))

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
                if hk:
                    # Capture variable in lambda default argument
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
