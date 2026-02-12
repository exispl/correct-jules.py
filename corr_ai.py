import time
import re
from openai import OpenAI, APIConnectionError, AuthenticationError, RateLimitError
from corr_config import cfg

class AIEngine:
    def __init__(self):
        self.client = None
        self.configure()

    def configure(self):
        key = cfg.config["api_key"]
        if not key: return False
        try:
            self.client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
            return True
        except Exception as e:
            print(f"AI Config Error: {e}")
            return False

    def process_text(self, action, text):
        if not self.client:
            if not self.configure(): return None, "Brak API Key"

        if text.strip() in cfg.session_ignored:
            return None, "Ignored"

        # Obsługa prefiksów tłumaczenia (np. "PL: Hello")
        target_lang_hint = ""
        clean_text = text

        if action == "TRANSLATE":
            # New tag logic: ;tag; e.g. ;en; ;tur;
            # Regex: look for start like ;xyz;
            tag_match = re.match(r"^;([a-zA-Z]+);\s*(.*)", text, re.DOTALL)
            if tag_match:
                tag = tag_match.group(1).lower()
                clean_text = tag_match.group(2)
                # Map simple tags
                lang_map = {
                    "en": "English", "pl": "Polish", "de": "German", "tur": "Turkish", "chi": "Chinese",
                    "es": "Spanish", "fr": "French", "ru": "Russian", "ua": "Ukrainian"
                }
                target_lang_hint = lang_map.get(tag, tag)
            else:
                # Old Regex "PL:"
                match = re.match(r"^([A-Z]{2,3}):\s*(.*)", text, re.DOTALL)
                if match:
                    lang_code = match.group(1).upper()
                    clean_text = match.group(2)
                    langs = {"PL": "Polish", "EN": "English", "DE": "German", "ES": "Spanish", "FR": "French", "IT": "Italian"}
                    target_lang_hint = langs.get(lang_code, lang_code)

        # Pobieramy prompty z konfiguracji
        prompts = cfg.config.get("prompts", {})

        system_prompt = ""
        if action == "TRANSLATE":
            if target_lang_hint:
                base = prompts.get("TRANSLATE_SPECIFIC", "Przetłumacz na {target_lang}.")
                system_prompt = base.replace("{target_lang}", target_lang_hint)
            else:
                system_prompt = prompts.get("TRANSLATE_AUTO", "Tłumacz.")
        else:
            # Domyślna obsługa dla CORRECT, SUMMARIZE, TONE_CHANGE, EXPLAIN itp.
            system_prompt = prompts.get(action, "Jesteś pomocnym asystentem.")

        try:
            print(f"AI Request: {action} | Hint: {target_lang_hint}")
            start_t = time.time()
            completion = self.client.chat.completions.create(
                model=cfg.config.get("model", "llama-3.3-70b-versatile"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": clean_text}
                ],
                temperature=0.3,
                max_tokens=2048
            )
            duration = time.time() - start_t
            return completion.choices[0].message.content.strip(), duration
        except AuthenticationError:
            return None, "Błędny klucz API (401)"
        except RateLimitError:
            return None, "Limit zapytań osiągnięty (429)"
        except APIConnectionError:
            return None, "Brak połączenia z internetem"
        except Exception as e:
            return None, f"Błąd: {str(e)}"

ai = AIEngine()
