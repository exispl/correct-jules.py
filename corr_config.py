import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
import queue
import warnings
import customtkinter as ctk

# --- KONFIGURACJA I STAŁE ---
warnings.filterwarnings("ignore")
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

CONFIG_FILE = "config.json"
HISTORY_FILE = "history.json"

# Lista nowoczesnych czcionek (system musi je mieć zainstalowane, inaczej fallback do Arial)
FONTS = ["Roboto", "Segoe UI", "Arial", "Helvetica", "Montserrat", "Lato", "Open Sans"]

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "llama-3.3-70b-versatile",  # Aktualny, szybki model Groq
    "hotkey_correct": "ctrl+F6",
    "hotkey_translate": "ctrl+F7",
    "hotkey_summarize": "ctrl+F8",
    "hotkey_tone": "ctrl+F9",
    "hotkey_explain": "ctrl+F10",
    "font_family": "Segoe UI",
    "font_size": 18,
    "theme": "Dark",
    "prompts": {
        "CORRECT": "Jesteś ekspertem językowym. Popraw błędy w tekście. Zwróć TYLKO poprawiony tekst.",
        "TRANSLATE_AUTO": "Jesteś tłumaczem. Jeśli tekst jest PL -> na EN. Jeśli inny -> na PL. Zwróć TYLKO tłumaczenie.",
        "TRANSLATE_SPECIFIC": "Jesteś tłumaczem. Przetłumacz tekst na język: {target_lang}. Zwróć TYLKO tłumaczenie.",
        "SUMMARIZE": "Jesteś asystentem. Streść podany tekst w kilku zdaniach. Zachowaj kluczowe informacje.",
        "TONE_CHANGE": "Jesteś redaktorem. Zmień ton tekstu na bardziej profesjonalny i uprzejmy. Zwróć TYLKO poprawiony tekst.",
        "EXPLAIN": "Jesteś programistą i nauczycielem. Wyjaśnij krótko i zwięźle, co robi ten kod. Jeśli to nie kod, wyjaśnij zagadnienie."
    },
    "models_list": [
        "llama-3.3-70b-versatile",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
        "gemma-7b-it"
    ]
}

# Global queue for GUI updates
gui_queue = queue.Queue()

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.history = []
        self.stats = {"corrected": 0, "translated": 0, "saved_time_s": 0, "words_corrected": 0}
        self.session_ignored = set()

        load_dotenv()
        self.env_key = os.getenv("GROQ_API_KEY") or os.getenv("GOOGLE_API_KEY")

        self.load_config()
        self.load_history()
        self.auto_replace = AutoReplaceManager()

        if not self.config["api_key"] and self.env_key:
            self.config["api_key"] = self.env_key

        self.load_themes()

    def load_themes(self):
        try:
            with open("themes.json", "r", encoding="utf-8") as f:
                self.themes = json.load(f)
        except Exception:
            self.themes = {} # Fallback

    def get_theme_colors(self):
        theme_name = self.config.get("theme", "Dark")
        if theme_name in self.themes:
            return self.themes[theme_name]
        # Default Dark theme fallback if json missing
        return {
            "fg_color": "#212121", "text_color": "white", "frame_color": "#333333",
            "button_color": "#2CC985", "button_hover": "#25A56D", "accent_text": "#2CC985",
            "bubble_bg": "#00695c", "bubble_hover": "#004d40", "input_bg": "#1a1a1a",
            "history_bg": "#2b2b2b"
        }

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except Exception: pass

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.history = data.get("history", [])
                    self.stats = data.get("stats", self.stats)
            except Exception: pass

    def save_history(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"history": self.history, "stats": self.stats}, f, indent=4, ensure_ascii=False)

    def add_history_entry(self, type_str, original, result, duration, diffs=None):
        entry = {
            "id": int(time.time() * 1000),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": type_str,
            "original": original,
            "result": result,
            "duration": round(duration, 3),
            "diffs": diffs if diffs else [] # Lista zmienionych słów
        }
        self.history.insert(0, entry)
        if len(self.history) > 50: self.history.pop()

        if type_str == "CORRECT": self.stats["corrected"] += 1
        elif type_str == "TRANSLATE": self.stats["translated"] += 1

        # Count words corrected
        if diffs:
            self.stats["words_corrected"] = self.stats.get("words_corrected", 0) + len(diffs)

        self.stats["saved_time_s"] += duration
        self.save_history()

class AutoReplaceManager:
    def __init__(self):
        self.file = "auto_replace.json"
        self.replacements = {}
        self.ignored = []
        self.load()

    def load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.replacements = data.get("replacements", {})
                    self.ignored = data.get("ignored", [])
            except: pass

    def save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump({"replacements": self.replacements, "ignored": self.ignored}, f, indent=4, ensure_ascii=False)

    def add_replacement(self, error, correct):
        if error.lower() == correct.lower(): return
        self.replacements[error] = correct
        if error in self.ignored: self.ignored.remove(error)
        self.save()

    def add_ignore(self, word):
        if word not in self.ignored:
            self.ignored.append(word)
        if word in self.replacements:
            del self.replacements[word]
        self.save()

cfg = ConfigManager()
