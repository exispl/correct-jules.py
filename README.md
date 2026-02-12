# AI Assistant Pro

Aplikacja asystenta AI z integracją systemową (skróty klawiszowe), korektą tekstu, tłumaczeniem, snippetsami i innymi funkcjami.

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
4. Skonfiguruj skróty klawiszowe (kliknij na przycisk "Brak" i wciśnij skrót).

## Funkcje

- **Korekta**: Poprawia błędy w zaznaczonym tekście (Ctrl+F6).
- **Tłumaczenie**: Tłumaczy zaznaczony tekst (automatycznie wykrywa język) (Ctrl+F7).
- **Streszczenie**: Tworzy podsumowanie zaznaczonego tekstu (Ctrl+F8).
- **Zmiana Tonu**: Zmienia styl tekstu na bardziej profesjonalny (Ctrl+F9).
- **Wyjaśnienie**: Wyjaśnia kod lub zagadnienie (Ctrl+F10).
- **Snippety**: Szybkie wklejanie tekstu i uruchamianie aplikacji. Wsparcie dla ikon z folderu (konfigurowalne w `config.json`).
- **Wysoka Widoczność**: Tryb "High Visibility" z dużymi czcionkami (19px+) i wysokim kontrastem.

## Zmiany w wersji v0.2.0

- Dodano tryb "High Visibility".
- Dodano zakładkę "Snippety" z obsługą ikon.
- Dodano "Click-to-bind" w ustawieniach skrótów.
- Dynamiczne skalowanie czcionek.
- Poprawki interfejsu.

## Skróty Klawiszowe (Domyślne)

- `Ctrl+F6`: Korekta
- `Ctrl+F7`: Tłumaczenie
- `Ctrl+F8`: Streszczenie
- `Ctrl+F9`: Zmiana Tonu
- `Ctrl+F10`: Wyjaśnienie
- `F1`: Pokaż okno aplikacji
