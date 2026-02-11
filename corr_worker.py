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
        threading.Thread(target=self._auto_replace_loop, daemon=True).start()

    def start_auto_replace_listener(self):
        # Only start if enabled, but for now we run it always or check flag inside
        self.tracking_enabled = True
        self.current_word = []
        # Use on_release to catch chars after they are typed
        keyboard.on_release(self._on_key_release)

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
        replacements = cfg.auto_replace.replacements
        if word in replacements:
            correct = replacements[word]

            # Wait a tiny bit to ensure 'space' was fully processed by the target app
            time.sleep(0.05)

            # Remove word + space
            n_back = len(word) + 1
            for _ in range(n_back):
                keyboard.send('backspace')
                time.sleep(0.005)

            # Type correct word + space
            keyboard.write(correct + " ")

            # Notify GUI via queue about auto-correction
            gui_queue.put(("STATUS", {"text": f"Auto-Korekta: {word} -> {correct}", "color": "#2CC985"}))

    def trigger(self, action_type):
        threading.Thread(target=self._process, args=(action_type,), daemon=True).start()

    def _process(self, action_type):
        time.sleep(0.05)
        keyboard.send('ctrl+c')
        time.sleep(0.1)
        text = pyperclip.paste()
        if not text.strip(): return

        res, dur = ai.process_text(action_type, text)
        if res:
            gui_queue.put(("POPUP", {"action": action_type, "org": text, "res": res, "dur": dur}))
        else:
            gui_queue.put(("STATUS", {"text": f"Błąd: {dur}", "color": "#FF4747"}))

worker = ActionWorker()
