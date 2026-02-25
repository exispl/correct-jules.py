# AGENTS.md

## Cursor Cloud specific instructions

### Overview

AI Assistant Pro is a Python GUI desktop application (CustomTkinter) that provides AI-powered text correction, translation, summarization, tone adjustment, and code explanation via the Groq API. It is designed for Windows but can run on Linux with the workarounds described below. See `README.md` for user-facing docs.

### Running in a headless Linux / container environment

- **Virtual display required**: Start Xvfb before launching the app: `Xvfb :99 -screen 0 1280x1024x24 &` then set `DISPLAY=:99`.
- **`keyboard` library needs root** and requires `/dev/input/event*` devices. In containers without real input devices or uinput kernel support, use the `dev_launcher.py` wrapper which patches the keyboard library to allow the GUI to start. Run: `sudo DISPLAY=:99 python3 dev_launcher.py`
- **System packages needed** (beyond pip deps): `python3-tk`, `gir1.2-gtk-3.0`, `gir1.2-ayatanaappindicator3-0.1`, `xclip`.
- **No linter, test suite, or build step** exists in this project — it is a single-entry-point Python application.

### Running the app

```bash
# Standard (requires keyboard device access and display)
sudo DISPLAY=:99 python3 dev_launcher.py

# Or natively on a Windows/Linux desktop with input devices:
python corr_main.py
```

### Key files

| File | Purpose |
|---|---|
| `corr_main.py` | Main entry point and GUI layout |
| `corr_config.py` | Configuration management (JSON files) |
| `corr_ai.py` | Groq API integration via OpenAI SDK |
| `corr_gui.py` | Custom widgets (BubbleButton, HistoryItem, popups) |
| `corr_worker.py` | Background worker for hotkeys and auto-replace |
| `dev_launcher.py` | Headless Linux launcher (patches keyboard lib) |
| `themes.json` | UI theme definitions |
| `snippets.json` | Sample snippet definitions |

### Gotchas

- The `keyboard` library assertion (`aggregate_devices`) fails in containers without `/dev/input/` event devices. The `dev_launcher.py` wrapper handles this.
- Global hotkey registration will show a "dumpkeys not found" error in the thread log on Linux — this is non-fatal and can be ignored.
- The app creates `config.json` and `history.json` at runtime (gitignored).
- The Groq API key is required for AI features but the app starts without one (shows a warning in the status bar).
