import threading
import time
import keyboard
import pyperclip
from corr_config import gui_queue, cfg
from corr_ai import ai

# --- WORKER ---
class ActionWorker:
    def __init__(self):
        self.start_auto_replace_listener()

    def start_auto_replace_listener(self):
        # Only start if enabled, but for now we run it always or check flag inside
        self.tracking_enabled = True
        self.current_word = []
        # Use on_release to catch chars after they are typed
        keyboard.on_release(self._on_key_release)

        # Register snippet hotkeys
        self._register_snippet_hotkeys()

    def _register_snippet_hotkeys(self):
        snippets = cfg.snippets.snippets
        for key, data in snippets.items():
            hk = data.get("hotkey")
            if hk:
                try:
                    # Bind hotkey to execute content based on type
                    keyboard.add_hotkey(hk, lambda k=key, d=data: self._execute_snippet(k, d))
                except: pass

        # Register Global Check Hotkey
        try:
            keyboard.add_hotkey("ctrl+shift+f9", lambda: self.trigger("CORRECT"))
        except: pass

    def _execute_snippet(self, key, data):
        content = data['content']
        type_s = data.get('type', 'text')

        # --- SCHEDULING CHECK ---
        schedule = data.get("schedule")
        if schedule:
            from datetime import datetime
            now = datetime.now()
            # Days
            if "days" in schedule and schedule["days"]:
                if now.weekday() not in schedule["days"]:
                    gui_queue.put(("STATUS", {"text": f"Snippet {key}: Zły dzień", "color": "orange"}))
                    return
            # Time
            try:
                s_str = schedule.get("start", "00:00")
                e_str = schedule.get("end", "23:59")
                s_t = datetime.strptime(s_str, "%H:%M").time()
                e_t = datetime.strptime(e_str, "%H:%M").time()
                curr_t = now.time()
                if not (s_t <= curr_t <= e_t):
                    gui_queue.put(("STATUS", {"text": f"Snippet {key}: Poza godzinami ({s_str}-{e_str})", "color": "orange"}))
                    return
            except: pass

        # --- ARGS CHECK ({}) ---
        if "{}" in content:
            import threading
            evt = threading.Event()
            res = []
            gui_queue.put(("INPUT", {"title": f"Argumenty: {key}", "prompt": "Wpisz wartość dla {}:", "event": evt, "result": res}))
            evt.wait() # Wait for UI thread
            if res and res[0]:
                content = content.replace("{}", res[0])
            else:
                gui_queue.put(("STATUS", {"text": "Anulowano (brak args)", "color": "orange"}))
                return

        time.sleep(0.1)

        if type_s == 'text':
            # NEW: Paste from clipboard for speed (as requested)
            try:
                import pyperclip
                pyperclip.copy(content)
                time.sleep(0.05) # Wait for clipboard to update
                keyboard.send('ctrl+v')
                gui_queue.put(("STATUS", {"text": f"Wklejono: {key}", "color": "#4aa3df"}))
            except Exception as e:
                # Fallback if clipboard fails
                keyboard.write(content)
                gui_queue.put(("STATUS", {"text": f"Wpisano (Fallback): {key}", "color": "#4aa3df"}))

        elif type_s == 'app':
            import subprocess, os
            try:
                # Try to run
                if os.path.exists(content):
                    os.startfile(content) # Windows specific, convenient
                else:
                    # Try subprocess for commands
                    subprocess.Popen(content, shell=True)
                gui_queue.put(("STATUS", {"text": f"Uruchomiono: {key}", "color": "#4aa3df"}))
            except Exception as e:
                # Try just run command if os.startfile fails or not windows
                try:
                    subprocess.Popen(content, shell=True)
                    gui_queue.put(("STATUS", {"text": f"Uruchomiono cmd: {key}", "color": "#4aa3df"}))
                except:
                    gui_queue.put(("STATUS", {"text": f"Błąd app: {e}", "color": "red"}))

        elif type_s == 'macro':
            # Send keys
            try:
                keyboard.send(content)
                gui_queue.put(("STATUS", {"text": f"Makro: {key}", "color": "#4aa3df"}))
            except Exception as e:
                gui_queue.put(("STATUS", {"text": f"Błąd makro: {e}", "color": "red"}))

    def _on_key_release(self, event):
        if not self.tracking_enabled: return

        try:
            if event.name == 'space':
                word = "".join(self.current_word)
                if word:
                    # Run replacement in thread to avoid blocking the hook
                    threading.Thread(target=self._perform_replace, args=(word,), daemon=True).start()
                self.current_word = []
            elif event.name == 'backspace':
                if self.current_word:
                    self.current_word.pop()
            elif len(event.name) == 1:
                self.current_word.append(event.name)
            elif event.name in ['enter', 'tab']:
                 self.current_word = []
        except Exception:
            self.current_word = []

    def _perform_replace(self, word):
        # 1. Check Auto-Replace
        replacements = cfg.auto_replace.replacements
        if word in replacements:
            correct = replacements[word]

            # Apply Text Cleaner (space before punctuation)
            # We assume word correction is a single word or short phrase
            # but if it has punctuation, cleaner will fix it.
            # Example: "word ," -> "word," logic.
            # Since we replace whole 'word' with 'correct', we can run cleaner on 'correct'
            # But the user also wants to fix "word ," typed manually.
            # Currently we only trigger on SPACE.

            # Let's apply cleaner to the correction output just in case
            correct = cfg.cleaner.clean(correct)

            self._backspace_and_write(word, correct + " ")
            gui_queue.put(("STATUS", {"text": f"Auto-Korekta: {word} -> {correct}", "color": "#2CC985"}))
            return

        # 2. Check Snippets (e.g. ;mail)
        snippets = cfg.snippets.snippets
        if word in snippets:
             # We need to execute based on type, but for text replacement we also need backspacing.
             # For app/macro, we might want to backspace the trigger too.
             # So let's backspace first, then execute.

             self._backspace_only(len(word) + 1) # +1 for space
             self._execute_snippet(word, snippets[word])
             return

    def _backspace_only(self, count):
        time.sleep(0.05)
        for _ in range(count):
            keyboard.send('backspace')
            time.sleep(0.005)

    def _backspace_and_write(self, old, new):
        time.sleep(0.05)
        n_back = len(old) + 1 # +1 for the space that triggered it
        for _ in range(n_back):
            keyboard.send('backspace')
            time.sleep(0.005)

        # Split new text by lines to handle multiline snippets correctly
        # keyboard.write handles newlines usually well but explicitly is safer
        keyboard.write(new)

    def trigger(self, action_type):
        threading.Thread(target=self._process, args=(action_type,), daemon=True).start()

    def _process(self, action_type):
        time.sleep(0.05)
        keyboard.send('ctrl+c')
        time.sleep(0.1)
        text = pyperclip.paste()
        if not text.strip(): return

        # Save original to history right away (so Win+V works if something goes wrong, or we just want to keep it)
        # Actually Windows clipboard history handles Ctrl+C automatically.
        # But user wants to ensure original is recoverable.
        # Since we just did Ctrl+C, it IS in the clipboard history stack.

        # Check for inline translation tags if action is generic or translate
        # If user pressed hotkey for correct but text has ;en;, maybe switch action?
        # For now, ai.process_text handles the tag extraction, so we just pass "TRANSLATE" if we detect tag?
        # User said "Wiedz, że masz przetłumaczyć".

        if ";" in text[:10]: # Quick check
             if any(tag in text[:10].lower() for tag in [";en;", ";pl;", ";de;", ";tur;", ";chi;"]):
                 action_type = "TRANSLATE"

        res, dur = ai.process_text(action_type, text)
        if res:
            gui_queue.put(("POPUP", {"action": action_type, "org": text, "res": res, "dur": dur}))
        else:
            gui_queue.put(("STATUS", {"text": f"Błąd: {dur}", "color": "#FF4747"}))

worker = ActionWorker()
