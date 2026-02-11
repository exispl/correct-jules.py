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
        self.geometry("1000x700")
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)

        self.tabs = {
            "Dash": self.tabview.add("Dashboard"),
            "Test": self.tabview.add("Strefa Testowa"),
            "Hist": self.tabview.add("Historia"),
            "Sett": self.tabview.add("Ustawienia"),
        }

        # Init Modules
        self.setup_dash()
        self.setup_test()
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

    # --- TEST ZONE (BUBBLES) ---
    def setup_test(self):
        f = self.tabs["Test"]
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1) # Output area expands

        # Input Area (Auto-expanding logic via weight)
        self.test_in = ctk.CTkTextbox(f, height=80, font=(cfg.config["font_family"], cfg.config["font_size"]))
        self.test_in.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        self.test_in.bind("<KeyRelease>", self.auto_resize_input)

        # Action Bar
        btn_frame = ctk.CTkFrame(f, fg_color="transparent")
        btn_frame.grid(row=1, column=0, pady=5)
        self.btn_check = ctk.CTkButton(btn_frame, text="✨ SPRAWDŹ (AI)", command=self.run_test, width=200, height=40, font=("Arial", 14, "bold"))
        self.btn_check.pack()

        # Output Area (Rich Text with Bubbles)
        # Używamy zwykłego Text z tkintera wewnątrz ramki CTk, bo CTkTextbox słabo obsługuje window_create
        self.out_frame = ctk.CTkFrame(f)
        self.out_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

        self.out_text = tk.Text(self.out_frame, bg="#2b2b2b", fg="white", font=(cfg.config["font_family"], cfg.config["font_size"]),
                                relief="flat", wrap="word", padx=10, pady=10)
        self.out_text.pack(fill="both", expand=True)

        # Context Menu
        self.menu = tk.Menu(self, tearoff=0, bg="#333", fg="white")

    def auto_resize_input(self, event):
        # Prosta logika: im więcej linii, tym wyższy widget (do limitu)
        lines = int(self.test_in.index('end-1c').split('.')[0])
        new_h = min(max(80, lines * 25), 200)
        if self.test_in.cget("height") != new_h:
            self.test_in.configure(height=new_h)

    def run_test(self):
        txt = self.test_in.get("0.0", "end").strip()
        if not txt: return
        self.status.configure(text="AI pracuje...", text_color="yellow")
        self.btn_check.configure(state="disabled")
        threading.Thread(target=self._thread_test, args=(txt,), daemon=True).start()

    def _thread_test(self, txt):
        try:
            res, dur = ai.process_text("CORRECT", txt)
            if res:
                self.after(0, lambda: self.render_bubbles(txt, res))
            else:
                gui_queue.put(("STATUS", {"text": f"Błąd: {dur}", "color": "red"}))
        finally:
            self.after(0, lambda: self.btn_check.configure(state="normal"))

    def render_bubbles(self, original, result):
        self.status.configure(text="Gotowe.", text_color="green")
        self.out_text.delete("1.0", "end")

        # Tokenizacja słowna
        orig_words = original.split()
        res_words = result.split()
        matcher = difflib.SequenceMatcher(None, orig_words, res_words)

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

        # Zapisz do historii
        cfg.add_history_entry("TEST", original, result, 0) # 0 bo nie mierzymy tu czasu sieci

    def show_bubble_menu(self, event, btn):
        self.menu.delete(0, "end")

        # 1. Sugestia AI (Domyślna)
        self.menu.add_command(label=f"✅ {btn.cget('text')} (Zatwierdź)",
                              command=lambda: self.resolve_bubble(btn, btn.cget('text')))

        self.menu.add_separator()

        # 2. Przywróć oryginał (jeśli był)
        if btn.original_text:
            self.menu.add_command(label=f"↩️ Przywróć: '{btn.original_text}'",
                                  command=lambda: self.resolve_bubble(btn, btn.original_text, is_revert=True))

        # 3. Edycja
        self.menu.add_command(label="✏️ Edytuj ręcznie...", command=lambda: self.manual_bubble_edit(btn))

        self.menu.tk_popup(event.x_root, event.y_root)

    def resolve_bubble(self, btn, text, is_revert=False):
        # Zamień widget na zwykły tekst
        # Musimy znaleźć indeks widgetu w tk.Text. To jest trudne.
        # Łatwiej: Po prostu nadpisz wygląd przycisku, żeby wyglądał jak tekst (hack)
        # ALBO: Nie usuwajmy go, tylko zmieńmy kolor na przezroczysty/szary.

        if is_revert:
            btn.configure(text=text, fg_color="transparent", hover=False, text_color="white")
        else:
            # Zatwierdzone - "rozpakuj" chmurkę wizualnie (zdejmij tło)
            btn.configure(fg_color="transparent", hover=False, text_color="white")

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

        ctk.CTkLabel(f, text="Czcionka interfejsu:").pack(anchor="w", padx=20)
        self.combo_font = ctk.CTkComboBox(f, values=FONTS, width=300)
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

    def save_sett(self):
        cfg.config["api_key"] = self.ent_api.get()
        cfg.config["model"] = self.combo_model.get()
        cfg.config["font_family"] = self.combo_font.get()

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
        f.grid_columnconfigure((0,1), weight=1)
        self.c1 = self._stat_card(f, "Korekty", 0, 0, 0)
        self.c2 = self._stat_card(f, "Tłumaczenia", 0, 0, 1)
        self.refresh_dash()

    def _stat_card(self, p, t, v, r, c):
        fr = ctk.CTkFrame(p, fg_color="#333"); fr.grid(row=r, column=c, padx=10, pady=10, sticky="ew")
        ctk.CTkLabel(fr, text=t).pack(pady=5)
        l = ctk.CTkLabel(fr, text=str(v), font=("Arial", 22, "bold"), text_color="#2CC985"); l.pack(pady=5)
        return l

    def refresh_dash(self):
        self.c1.configure(text=str(cfg.stats["corrected"]))
        self.c2.configure(text=str(cfg.stats["translated"]))

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
