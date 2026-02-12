import os
import json
import time
from datetime import datetime, timedelta
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

FONTS = ["Roboto", "Segoe UI", "Arial", "Helvetica", "Montserrat", "Lato", "Open Sans"]

DEFAULT_CONFIG = {
    "api_key": "",
    "model": "llama-3.3-70b-versatile",
    "hotkey_correct": "CTRL + F6",
    "hotkey_translate": "CTRL + F7",
    "hotkey_summarize": "CTRL + F8",
    "hotkey_tone": "CTRL + F9",
    "hotkey_explain": "CTRL + F10",
    "font_family": "Segoe UI",
    "font_size": 18,
    "theme": "Light",
    "icons_path": "D:\\exis\\Icons",
    "disabled_functions": {}, # key: timestamp (float)
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

gui_queue = queue.Queue()

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.history = []
        self.stats = {"corrected": 0, "translated": 0, "saved_time_s": 0, "words_corrected": 0}
        self.session_ignored = set()
        self.user_profile = {"name": "Gość", "email": "", "photo": "", "logged_in": False}

        load_dotenv()
        self.env_key = os.getenv("GROQ_API_KEY") or os.getenv("GOOGLE_API_KEY")

        self.load_config()
        self.load_history()
        self.load_profile()
        self.auto_replace = AutoReplaceManager()

        if not self.config["api_key"] and self.env_key:
            self.config["api_key"] = self.env_key

        self.load_themes()

        # Ensure new keys
        if "disabled_functions" not in self.config:
            self.config["disabled_functions"] = {}

    def load_themes(self):
        try:
            with open("themes.json", "r", encoding="utf-8") as f:
                self.themes = json.load(f)
        except Exception:
            self.themes = {}

    def get_theme_colors(self):
        theme_name = self.config.get("theme", "Light")
        if theme_name in self.themes:
            return self.themes[theme_name]
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

    def load_profile(self):
        if os.path.exists("profile.json"):
            try:
                with open("profile.json", "r", encoding="utf-8") as f:
                    self.user_profile = json.load(f)
            except: pass

    def save_profile(self):
        with open("profile.json", "w", encoding="utf-8") as f:
            json.dump(self.user_profile, f, indent=4)

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

    def get_version(self):
        return "v0.2.1"

    def add_history_entry(self, type_str, original, result, duration, diffs=None):
        entry = {
            "id": int(time.time() * 1000),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": type_str,
            "original": original,
            "result": result,
            "duration": round(duration, 3),
            "diffs": diffs if diffs else []
        }
        self.history.insert(0, entry)
        if len(self.history) > 50: self.history.pop()

        if type_str == "CORRECT": self.stats["corrected"] += 1
        elif type_str == "TRANSLATE": self.stats["translated"] += 1

        if diffs:
            self.stats["words_corrected"] = self.stats.get("words_corrected", 0) + len(diffs)

        self.stats["saved_time_s"] += duration
        self.save_history()

    def disable_function(self, func_name, hours=None):
        if hours is None: # Until restart (special value -1 or just volatile)
            # Actually user wants "until restart".
            # If we save to file, it persists.
            # So "until restart" means we set a flag in memory OR timestamp=0 and handle it on load?
            # Easiest: timestamp 0 = disabled until restart. Cleared on init?
            # Wait, init loads from file. If we save 0, it persists.
            # So for "until restart", we should NOT save to file, or save a special marker.
            # Let's use a memory-only set for "until restart".
            self.session_disabled_funcs = getattr(self, "session_disabled_funcs", set())
            self.session_disabled_funcs.add(func_name)
            return

        # Permanent / Timed
        if hours == -1: # Forever (until manually enabled)
             exp = 9999999999.9
        else:
             exp = time.time() + (hours * 3600)

        self.config["disabled_functions"][func_name] = exp
        self.save_config()

    def is_function_enabled(self, func_name):
        # 1. Check session disable
        if hasattr(self, "session_disabled_funcs") and func_name in self.session_disabled_funcs:
            return False

        # 2. Check config disable
        if func_name in self.config["disabled_functions"]:
            exp = self.config["disabled_functions"][func_name]
            if time.time() < exp:
                return False
            else:
                # Expired
                del self.config["disabled_functions"][func_name]
                self.save_config()

        return True

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

class TextCleaner:
    def clean(self, text):
        text = " ".join(text.split())
        text = text.replace(" ,", ",").replace(" .", ".").replace(" !", "!").replace(" ?", "?")
        return text

class SnippetManager:
    def __init__(self):
        self.file = "snippets.json"
        self.snippets = {}
        self.load()

    def load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, "r", encoding="utf-8") as f:
                    self.snippets = json.load(f)
            except: pass

    def save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.snippets, f, indent=4, ensure_ascii=False)

    def add_snippet(self, key, content, type="text", hotkey=None, schedule=None):
        """
        schedule: dict {"start": "HH:MM", "end": "HH:MM", "days": [0,1,2...]} or None
        """
        self.snippets[key] = {
            "content": content,
            "type": type,
            "hotkey": hotkey,
            "schedule": schedule
        }
        self.save()

    def remove_snippet(self, key):
        if key in self.snippets:
            del self.snippets[key]
            self.save()

cfg = ConfigManager()
cfg.cleaner = TextCleaner()
cfg.snippets = SnippetManager()
