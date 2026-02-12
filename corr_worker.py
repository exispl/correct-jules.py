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
                    # Bind hotkey to paste content
                    # We use a lambda to capture content
                    keyboard.add_hotkey(hk, lambda c=data['content']: self._paste_snippet(c))
                except: pass

        # Register Global Check Hotkey
        try:
            keyboard.add_hotkey("ctrl+shift+f9", lambda: self.trigger("CORRECT"))
        except: pass

    def _paste_snippet(self, content):
        # Simply write content
        time.sleep(0.1)
        keyboard.write(content)
        gui_queue.put(("STATUS", {"text": "Wstawiono snippet (skrót)", "color": "#4aa3df"}))

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
             content = snippets[word]['content']
             self._backspace_and_write(word, content)
             gui_queue.put(("STATUS", {"text": f"Snippet: {word}", "color": "#4aa3df"}))
             return

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
