# Praca we dwóch na GitHubie

## Właściciele
- **Osoba 1 (kolega):** `camera-agent/` — OpenCV, YOLO, tracking, MQTT agent, LIVE/REPLAY.
- **Osoba 2 (Kamil):** `backend/` i `frontend/` — ADS-B, identyfikacja, baza, FastAPI, React.
- **Wspólnie:** `shared/contracts/`, `infrastructure/`, `docs/` i testy integracyjne.

Właściciel folderu odpowiada za review zmian, ale nie blokuje pomocy drugiej osoby.

## Workflow
1. **Wspólnie** zatwierdźcie kontrakty MQTT przed pisaniem logiki zależnej od danych.
2. Jedno zadanie = jeden GitHub Issue = krótki branch (np. `feat/cv-detector`, `feat/adsb-client`).
3. Pull Request wskazuje Issue i opisuje sposób testowania; unikajcie bezpośrednich commitów na `main`.
4. Druga osoba przegląda PR, szczególnie jeżeli zmienia `shared/contracts/`.
5. Po integracji wykonajcie szybki test na 2 urządzeniach.

## Niezależna implementacja
- Osoba 1 uruchamia pipeline z MP4 i może wysyłać testowe payloady, zanim będzie miała model detekcji.
- Osoba 2 zasilą backend przez dane z `shared/examples/`, zanim agent zacznie działać.
- Nie należy robić dwóch niezależnych implementacji agenta dla dwóch kamer.

## Etapy
- **M1** — kontrakt i MQTT end-to-end.
- **M2** — detekcja MP4 + SQLite.
- **M3** — ADS-B + kandydaci lotów.
- **M4** — React, sterowanie i pełny REPLAY.
- **M5** — testy integracyjne i prezentacja.

[Backlog](backlog.md) i [GitHub Issues](https://github.com/kamilklepusewicz/skywatch-iot/issues).
