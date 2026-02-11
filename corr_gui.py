import customtkinter as ctk
import tkinter as tk
import time
import difflib
import pyperclip
import keyboard
from corr_config import cfg, gui_queue

# --- CUSTOM WIDGETS ---
class BubbleButton(ctk.CTkButton):
    """Przycisk udający tag HTML (chmurkę)"""
    def __init__(self, parent, text, original_text, command=None, **kwargs):
        colors = cfg.get_theme_colors()
        font_cfg = (cfg.config["font_family"], cfg.config["font_size"] - 2)
        super().__init__(parent, text=text, font=font_cfg,
                         fg_color=colors.get("bubble_bg", "#00695c"),
                         hover_color=colors.get("bubble_hover", "#004d40"),
                         text_color="white", # Contrast text for buttons usually white
                         height=24, corner_radius=12, width=len(text)*10 + 20,
                         command=command, **kwargs)
        self.original_text = original_text

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
        ctk.CTkLabel(self.header, text=dt_str, text_color="gray", font=("Arial", 10)).pack(side="right")

        # Details (hidden by default)
        self.details = ctk.CTkFrame(self, fg_color="transparent")

        # Original
        ctk.CTkLabel(self.details, text="Oryginał:", text_color="gray", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(5,0))
        self.orig_box = ctk.CTkTextbox(self.details, height=50, fg_color=colors.get("input_bg"), text_color=colors.get("text_color"), font=("Arial", 12))
        self.orig_box.pack(fill="x", padx=10, pady=2)

        # Result
        ctk.CTkLabel(self.details, text="Wynik:", text_color="gray", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(5,0))
        self.res_box = ctk.CTkTextbox(self.details, height=50, fg_color=colors.get("input_bg"), text_color=colors.get("text_color"), font=("Arial", 12))
        self.res_box.pack(fill="x", padx=10, pady=2)

        # Diff list - now with more visual punch
        if data['diffs']:
            ctk.CTkLabel(self.details, text="Zmiany (Słowo po słowie):", text_color=colors.get("accent_text"), font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(5,0))
            self.diff_frame = ctk.CTkFrame(self.details, fg_color=colors.get("input_bg"))
            self.diff_frame.pack(fill="x", padx=10, pady=5)

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

                        # Old Word (Red)
                        ctk.CTkLabel(row, text=d['old'], text_color="#FF4747", font=("Consolas", 14, "bold"), width=120, anchor="e").pack(side="left")

                        # Arrow
                        ctk.CTkLabel(row, text="➡", font=("Arial", 14), width=30).pack(side="left")

                        # New Word (Green)
                        ctk.CTkLabel(row, text=d['new'], text_color="#2CC985", font=("Consolas", 14, "bold"), width=120, anchor="w").pack(side="left")

                        # Context (fragment) - optional, can be complex to calculate index

            self.expanded = True

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
        self.review_list = review_list # List of (old, new) tuples
        self.index = 0
        self.title("Szybki Przegląd Słówek")
        self.geometry("400x300")
        self.attributes("-topmost", True)

        colors = cfg.get_theme_colors()
        self.configure(fg_color=colors.get("fg_color"))

        self.lbl_counter = ctk.CTkLabel(self, text="0/0", text_color="gray")
        self.lbl_counter.pack(pady=5)

        self.card_frame = ctk.CTkFrame(self, fg_color=colors.get("frame_color"), corner_radius=15)
        self.card_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Use Textbox for multi-line support if needed, but Label is cleaner for single words
        # We will try dynamic font sizing in show_current
        self.lbl_bad = ctk.CTkLabel(self.card_frame, text="", font=("Arial", 32, "bold"), text_color="#FF4747", wraplength=380)
        self.lbl_bad.pack(expand=True, pady=10)

        ctk.CTkLabel(self.card_frame, text="⬇️", font=("Arial", 24)).pack()

        self.lbl_good = ctk.CTkLabel(self.card_frame, text="", font=("Arial", 32, "bold"), text_color="#2CC985", wraplength=380)
        self.lbl_good.pack(expand=True, pady=10)

        help_lbl = ctk.CTkLabel(self, text="[➡] Akceptuj   [⬅] Odrzuć   [⬇] Pomiń", text_color="gray", font=("Consolas", 10))
        help_lbl.pack(pady=10)

        self.bind("<Right>", lambda e: self.action_accept())
        self.bind("<Left>", lambda e: self.action_reject())
        self.bind("<Down>", lambda e: self.action_skip())

        self.show_current()

    def show_current(self):
        if self.index >= len(self.review_list):
            self.destroy()
            return

        old, new = self.review_list[self.index]

        # Dynamic font sizing
        # Base size 32. Reduce if long.
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
