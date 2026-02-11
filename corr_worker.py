import threading
import time
import keyboard
import pyperclip
from corr_config import gui_queue
from corr_ai import ai

# --- WORKER ---
class ActionWorker:
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
