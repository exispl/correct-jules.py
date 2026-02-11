# AI Assistant Pro

Aplikacja asystenta AI z integracją systemową (skróty klawiszowe), korektą tekstu, tłumaczeniem i innymi funkcjami.

## Wymagania

- Python 3.10+
- Klucz API Groq (lub kompatybilny z OpenAI)

## Instalacja

1. Sklonuj repozytorium.
2. Zainstaluj zależności:
   ```bash
   pip install -r requirements.txt
   ```

## Uruchomienie

Uruchom plik `corr_main.py`:

```bash
python corr_main.py
```

## Konfiguracja

1. Po uruchomieniu przejdź do zakładki **Ustawienia**.
2. Wpisz swój klucz API Groq.
3. Wybierz model AI.
4. Skonfiguruj skróty klawiszowe (domyślnie `Ctrl+F6` dla korekty, `Ctrl+F7` dla tłumaczenia).

## Funkcje

- **Korekta**: Poprawia błędy w zaznaczonym tekście.
- **Tłumaczenie**: Tłumaczy zaznaczony tekst (automatycznie wykrywa język).
- **Streszczenie**: Tworzy podsumowanie zaznaczonego tekstu.
- **Zmiana Tonu**: Zmienia styl tekstu na bardziej profesjonalny.
- **Wyjaśnienie**: Wyjaśnia kod lub zagadnienie.

## Skróty Klawiszowe (Domyślne)

- `Ctrl+F6`: Korekta
- `Ctrl+F7`: Tłumaczenie
- `Ctrl+F8`: Streszczenie
- `Ctrl+F9`: Zmiana Tonu
- `Ctrl+F10`: Wyjaśnienie
- `F1`: Pokaż okno aplikacji
