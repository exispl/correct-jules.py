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
        font_cfg = (cfg.config["font_family"], cfg.config["font_size"] - 2)
        super().__init__(parent, text=text, font=font_cfg,
                         fg_color="#00695c", hover_color="#004d40",
                         height=24, corner_radius=12, width=len(text)*10 + 20,
                         command=command, **kwargs)
        self.original_text = original_text

class HistoryItem(ctk.CTkFrame):
    """Zwijany element historii"""
    def __init__(self, parent, data):
        super().__init__(parent, fg_color="#2b2b2b", corner_radius=6)
        self.data = data
        self.expanded = False

        # Header
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=5, pady=5)
        self.header.bind("<Button-1>", self.toggle)

        type_color = "#2CC985" if data['type'] == "CORRECT" else "#4aa3df"
        ctk.CTkLabel(self.header, text=f"[{data['type']}]", text_color=type_color, width=60, font=("Consolas", 11, "bold")).pack(side="left")

        summary = data['result'][:50] + "..." if len(data['result']) > 50 else data['result']
        self.lbl_summary = ctk.CTkLabel(self.header, text=summary, anchor="w", cursor="hand2")
        self.lbl_summary.pack(side="left", fill="x", expand=True, padx=5)
        self.lbl_summary.bind("<Button-1>", self.toggle)

        ctk.CTkLabel(self.header, text=data['time'][11:16], text_color="gray").pack(side="right")

        # Details (hidden by default)
        self.details = ctk.CTkFrame(self, fg_color="#202020")

        # Original vs Result
        ctk.CTkLabel(self.details, text="Oryginał:", text_color="gray", font=("Arial", 10)).pack(anchor="w", padx=10, pady=(5,0))
        ctk.CTkTextbox(self.details, height=60, fg_color="#1a1a1a").pack(fill="x", padx=10, pady=2)
        # (Wstawianie tekstu zrobimy przy rozwijaniu żeby nie mulić startu)

        # Lista zmian
        if data['diffs']:
            ctk.CTkLabel(self.details, text="Zmiany:", text_color="#ffcc00", font=("Arial", 10)).pack(anchor="w", padx=10, pady=(5,0))
            self.diff_box = ctk.CTkTextbox(self.details, height=80, fg_color="#1a1a1a")
            self.diff_box.pack(fill="x", padx=10, pady=5)

    def toggle(self, event=None):
        if self.expanded:
            self.details.pack_forget()
            self.expanded = False
        else:
            self.details.pack(fill="x", padx=5, pady=5)

            # Populate textboxes only when expanded
            orig_box = self.details.winfo_children()[1]
            if orig_box.get("0.0", "end").strip() == "":
                orig_box.insert("0.0", self.data['original'])
                orig_box.configure(state="disabled")

                if self.data['diffs']:
                    self.diff_box.configure(state="normal")
                    self.diff_box.delete("0.0", "end")
                    for d in self.data['diffs']:
                        self.diff_box.insert("end", f"🔴 {d['old']}  ->  🟢 {d['new']}\n")
                    self.diff_box.configure(state="disabled")

            self.expanded = True

# --- POPUP ---
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
