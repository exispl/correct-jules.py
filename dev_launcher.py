"""
Development launcher for running AI Assistant Pro in a headless Linux environment.
Patches the `keyboard` library to work without physical input devices (required for
Xvfb / container environments where /dev/input and /dev/uinput are unavailable).
"""
import sys
import types

import keyboard
import keyboard._nixcommon as _nixcommon
import keyboard._nixkeyboard as _nixkeyboard

_original_aggregate = _nixcommon.aggregate_devices

class _FakeDevice:
    def __init__(self):
        self._listeners = []

    def read_event(self):
        import time
        while True:
            time.sleep(3600)

    def write_event(self, *args, **kwargs):
        pass

def _patched_aggregate(type_name):
    return _FakeDevice()

_nixcommon.aggregate_devices = _patched_aggregate
_nixkeyboard.aggregate_devices = _patched_aggregate

_original_init = _nixkeyboard.init
_inited = False

def _patched_init():
    global _inited
    if _inited:
        return
    _inited = True
    _nixkeyboard.device = _FakeDevice()

_nixkeyboard.init = _patched_init
keyboard._os_keyboard.init = _patched_init

if __name__ == "__main__":
    from corr_main import MainApp
    app = MainApp()
    app.mainloop()
