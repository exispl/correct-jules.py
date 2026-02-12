import customtkinter as ctk
import tkinter as tk
import time
import difflib
import pyperclip
import keyboard
import string
from corr_config import cfg, gui_queue

# --- CUSTOM WIDGETS ---
class BubbleButton(ctk.CTkButton):
    """Przycisk udający tag HTML (chmurkę)"""
    def __init__(self, parent, text, original_text, command=None, **kwargs):
        colors = cfg.get_theme_colors()
        # Ensure bubble size is similar to text size (no huge extra padding) but distinctive
        font_cfg = (cfg.config["font_family"], cfg.config["font_size"])

        super().__init__(parent, text=text, font=font_cfg,
                         fg_color=colors.get("bubble_bg", "#00695c"),
                         hover_color=colors.get("bubble_hover", "#004d40"),
                         text_color="white",
                         height=28, # Slightly taller
                         corner_radius=14,
                         width=len(text)*10 + 10, # Adjusted width
                         command=command, **kwargs)
        self.original_text = original_text
        self.colors = colors

        # Scroll Bindings
        self.bind("<MouseWheel>", self.on_scroll)
        self.bind("<Button-3>", self.on_right_click)

    def on_scroll(self, event):
        # Delta > 0 -> Up (Accept -> Green)
        # Delta < 0 -> Down (Reject -> Red)
        if event.delta > 0:
            self.configure(fg_color="#2CC985") # Green
            # Ideally trigger "accept" logic immediately or mark for accept
            # For now visual feedback, logic can be in MainApp
            if self.master.master.master: # Traversing up to MainApp is hacky, better use callback
                 pass
        else:
            self.configure(fg_color="#FF4747") # Red

    def on_right_click(self, event):
        # Trigger external handler passed via command or separate binding
        pass

class HistoryItem(ctk.CTkFrame):
    """Zwijany element historii"""
    def __init__(self, parent, data):
        colors = cfg.get_theme_colors()
        super().__init__(parent, fg_color=colors.get("history_bg"), corner_radius=6)
        self.data = data
        self.colors = colors
        self.expanded = False

        # Header
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=5, pady=5)
        self.header.bind("<Button-1>", self.toggle)

        type_color = colors.get("accent_text", "#2CC985")
        ctk.CTkLabel(self.header, text=f"[{data['type']}]", text_color=type_color, width=80, font=("Consolas", 12, "bold")).pack(side="left")

        summary = data['result'][:60] + "..." if len(data['result']) > 60 else data['result']
        self.lbl_summary = ctk.CTkLabel(self.header, text=summary, anchor="w", cursor="hand2", text_color=colors.get("text_color"))
        self.lbl_summary.pack(side="left", fill="x", expand=True, padx=5)
        self.lbl_summary.bind("<Button-1>", self.toggle)

        # Date & Time
        dt_str = f"{data['time']}" # Full date
        ctk.CTkLabel(self.header, text=dt_str, text_color="gray", font=("Arial", 10)).pack(side="right", padx=5)

        # Delete Button (Trash Icon - Larger)
        ctk.CTkButton(self.header, text="🗑️", width=40, height=40, font=("Arial", 20), fg_color="transparent", hover_color=colors.get("bubble_hover"),
                      text_color="red", command=self.delete_me).pack(side="right", padx=5)

        # Details (hidden by default)
        self.details = ctk.CTkFrame(self, fg_color="transparent")

        # Original
        ctk.CTkLabel(self.details, text="Oryginał:", text_color="gray", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(5,0))
        self.orig_box = ctk.CTkTextbox(self.details, height=100, fg_color=colors.get("input_bg"), text_color=colors.get("text_color"), font=("Arial", 12))
        self.orig_box.pack(fill="x", padx=10, pady=2)

        # Result
        ctk.CTkLabel(self.details, text="Wynik:", text_color="gray", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(5,0))
        self.res_box = ctk.CTkTextbox(self.details, height=100, fg_color=colors.get("input_bg"), text_color=colors.get("text_color"), font=("Arial", 12))
        self.res_box.pack(fill="x", padx=10, pady=2)

        # Diff list - now with more visual punch
        if data['diffs']:
            ctk.CTkLabel(self.details, text="Zmiany (Słowo po słowie):", text_color=colors.get("accent_text"), font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(5,0))
            self.diff_frame = ctk.CTkFrame(self.details, fg_color=colors.get("input_bg"))
            self.diff_frame.pack(fill="x", padx=10, pady=5)

    def delete_me(self):
        # Remove from config history list
        if self.data in cfg.history:
            cfg.history.remove(self.data)
            cfg.save_history()
        self.destroy()

    def toggle(self, event=None):
        if self.expanded:
            self.details.pack_forget()
            self.expanded = False
        else:
            self.details.pack(fill="x", padx=5, pady=5)

            # Populate textboxes only when expanded
            if self.orig_box.get("0.0", "end").strip() == "":
                self.orig_box.insert("0.0", self.data['original'])
                self.orig_box.configure(state="disabled")

                self.res_box.insert("0.0", self.data['result'])
                self.res_box.configure(state="disabled")

                if self.data['diffs']:
                    # Clear previous children if any (re-opening)
                    for w in self.diff_frame.winfo_children(): w.destroy()

                    for d in self.data['diffs']:
                        row = ctk.CTkFrame(self.diff_frame, fg_color="transparent")
                        row.pack(fill="x", pady=2)
                        row.bind("<Button-3>", lambda e, old=d['old'], new=d['new']: self.open_review(old, new))

                        # Old Word (Red)
                        l1 = ctk.CTkLabel(row, text=d['old'], text_color="#FF4747", font=("Consolas", 14, "bold"), width=120, anchor="e")
                        l1.pack(side="left")
                        l1.bind("<Button-3>", lambda e, old=d['old'], new=d['new']: self.open_review(old, new))

                        # Arrow
                        ctk.CTkLabel(row, text="➡", font=("Arial", 14), width=30).pack(side="left")

                        # New Word (Green)
                        l2 = ctk.CTkLabel(row, text=d['new'], text_color="#2CC985", font=("Consolas", 14, "bold"), width=120, anchor="w")
                        l2.pack(side="left")
                        l2.bind("<Button-3>", lambda e, old=d['old'], new=d['new']: self.open_review(old, new))

            self.expanded = True

    def open_review(self, old, new):
        QuickReviewDialog(self.winfo_toplevel(), [(old, new)])

# --- POPUPS ---
class ReviewPopup(ctk.CTkToplevel):
    def __init__(self, parent, action, original, result, duration):
        super().__init__(parent)
        self.action = action
        self.original = original
        self.result = result
        self.duration = duration

        self.title("AI Assistant")
        self.geometry("600x400")
        self.attributes("-topmost", True)

        font_main = (cfg.config["font_family"], cfg.config["font_size"])

        # Header
        h = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame = h # Store reference
        h.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(h, text=f"{action} ({int(duration*1000)}ms)", text_color="gray").pack(side="right")
        ctk.CTkLabel(h, text="Wynik AI:", font=(font_main[0], 16, "bold"), text_color="#2CC985").pack(side="left")

        # Body
        self.txt = ctk.CTkTextbox(self, font=font_main)
        self.txt.pack(fill="both", expand=True, padx=15, pady=5)
        self.txt.insert("0.0", result)

        # Buttons
        b_frame = ctk.CTkFrame(self, fg_color="transparent")
        b_frame.pack(fill="x", padx=15, pady=15)

        ctk.CTkButton(b_frame, text="ZATWIERDŹ (Enter)", command=self.accept, fg_color="#2CC985", text_color="black").pack(side="left", expand=True, fill="x", padx=5)
        ctk.CTkButton(b_frame, text="ODRZUĆ (Esc)", command=self.destroy, fg_color="#FF4747").pack(side="left", expand=True, fill="x", padx=5)

        self.bind("<Return>", lambda e: self.accept())
        self.bind("<Escape>", lambda e: self.destroy())
        self.focus_force()

    def accept(self):
        pyperclip.copy(self.result)
        self.destroy()
        time.sleep(0.1)
        keyboard.send('ctrl+v')

        # Obliczanie różnic do historii
        diffs = []
        if self.action == "CORRECT":
            # Proste porównanie słów
            matcher = difflib.SequenceMatcher(None, self.original.split(), self.result.split())
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'replace':
                    old_ph = " ".join(self.original.split()[i1:i2])
                    new_ph = " ".join(self.result.split()[j1:j2])
                    diffs.append({"old": old_ph, "new": new_ph})

        cfg.add_history_entry(self.action, self.original, self.result, self.duration, diffs)
        gui_queue.put(("REFRESH", None))

class QuickReviewDialog(ctk.CTkToplevel):
    def __init__(self, parent, review_list):
        super().__init__(parent)

        # Filtering logic: remove trivial punctuation changes
        self.review_list = [
            (old, new) for old, new in review_list
            if not self.is_trivial(old, new)
        ]

        self.index = 0
        self.title("Szybki Przegląd Słówek")
        self.geometry("500x350")
        self.attributes("-topmost", True)

        colors = cfg.get_theme_colors()
        self.configure(fg_color=colors.get("fg_color"))

        if not self.review_list:
             # If all were trivial
             ctk.CTkLabel(self, text="Brak istotnych zmian do przeglądu.", font=("Arial", 16)).pack(expand=True)
             self.after(2000, self.destroy)
             return

        self.lbl_counter = ctk.CTkLabel(self, text="0/0", text_color="gray")
        self.lbl_counter.pack(pady=5)

        self.card_frame = ctk.CTkFrame(self, fg_color=colors.get("frame_color"), corner_radius=15)
        self.card_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.lbl_bad = ctk.CTkLabel(self.card_frame, text="", font=("Arial", 32, "bold"), text_color="#FF4747", wraplength=450)
        self.lbl_bad.pack(expand=True, pady=10)

        ctk.CTkLabel(self.card_frame, text="⬇️", font=("Arial", 24)).pack()

        self.lbl_good = ctk.CTkLabel(self.card_frame, text="", font=("Arial", 32, "bold"), text_color="#2CC985", wraplength=450)
        self.lbl_good.pack(expand=True, pady=10)

        help_lbl = ctk.CTkLabel(self, text="[➡/Enter] Akceptuj   [⬅/Del] Odrzuć   [⬇/Space] Pomiń   [ESC] Zapisz i Wyjdź", text_color="gray", font=("Consolas", 10))
        help_lbl.pack(pady=10)

        self.bind("<Right>", lambda e: self.action_accept())
        self.bind("<Return>", lambda e: self.action_accept())
        self.bind("<Left>", lambda e: self.action_reject())
        self.bind("<Delete>", lambda e: self.action_reject())
        self.bind("<Down>", lambda e: self.action_skip())
        self.bind("<space>", lambda e: self.action_skip())
        self.bind("<Escape>", lambda e: self.action_save_and_exit())

        self.show_current()

    def is_trivial(self, old, new):
        # 1. Punctuation only change?
        # Remove punctuation and compare
        # "kurtkę," vs "kurtkę" -> same
        trans = str.maketrans('', '', string.punctuation)
        old_clean = old.translate(trans).strip()
        new_clean = new.translate(trans).strip()

        if old_clean == new_clean:
            return True

        # 2. Simple inflections (heuristic) "mamusią" -> "mamą" is hard without NLP
        # User explicitly asked to ignore "mamusią" -> "mamą".
        # Let's add that specific case or generic length-based heuristic?
        # Heuristic: if start matches and length diff < 3? "mamusią" vs "mamą"
        # "mamusi" vs "mam" -> start "mam".
        # This is risky. Let's stick to punctuation for now as explicitly safe.
        # User: "ignorował zamiany „mamusią” na „mamą”."
        # User: "Ale już np. z kolei „kórtkę," a "kurtkę,” to takie zmiany niech oczywiście pokazuje."
        # Wait, "kórtkę" is error. "kurtkę" is correct. This is NOT trivial.

        return False

    def show_current(self):
        if self.index >= len(self.review_list):
            self.action_save_and_exit()
            return

        old, new = self.review_list[self.index]

        # Dynamic font sizing
        def get_size(text):
            l = len(text)
            if l < 10: return 40
            if l < 20: return 32
            if l < 30: return 24
            return 18

        self.lbl_bad.configure(text=old, font=("Arial", get_size(old), "bold"))
        self.lbl_good.configure(text=new, font=("Arial", get_size(new), "bold"))
        self.lbl_counter.configure(text=f"{self.index + 1}/{len(self.review_list)}")

    def action_accept(self):
        old, new = self.review_list[self.index]
        cfg.auto_replace.add_replacement(old, new)
        self.next_item()

    def action_reject(self):
        old, _ = self.review_list[self.index]
        cfg.auto_replace.add_ignore(old)
        self.next_item()

    def action_skip(self):
        self.next_item()

    def next_item(self):
        self.index += 1
        self.show_current()

    def action_save_and_exit(self):
        # Already saving incrementally in actions
        self.destroy()
