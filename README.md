# SkyWatch IoT

**Projekt zaliczeniowy — Usługi i aplikacje Internetu Rzeczy**

SkyWatch IoT to rozproszony prototyp obserwacji nieba: dwa fizyczne urządzenia z kamerami wykrywają obiekty (LIVE lub REPLAY), przekazują zdarzenia przez MQTT, a backend z dashboardem prezentują obserwacje oraz kandydatów na loty z danych ADS-B.

> **Status:** [camera-agent (osoba 1)](camera-agent/README.md) ma implementację LIVE/REPLAY, detekcji, trackingu i MQTT oraz testy techniczne. Walidacja na rzeczywistych nagraniach i dwóch laptopach pozostaje do wykonania. Backend i frontend są nadal szkieletem. Przykłady i generowane filmy są danymi demonstracyjnymi.

## MVP
1. Jeden konfigurowalny `camera-agent` uruchamiany na **dwóch laptopach** (różne `camera_id`).
2. Agent obsługuje LIVE (kamera) i REPLAY (MP4), generuje detekcje oraz przesyła statusy i zdarzenia przez MQTT.
3. FastAPI odbiera i zapisuje obserwacje w SQLite oraz wysyła do agentów komendy z potwierdzeniem ACK.
4. Backend pobiera pobliskie loty z ADS-B lub historyczne snapshoty dla REPLAY i wyznacza **kandydatów**, nie gwarantując identyfikacji.
5. React pokazuje kamery, historię, kandydatów, mapę i zdalne sterowanie.
6. Prezentację można wykonać offline w REPLAY, korzystając z nagranych wideo i zsynchronizowanych danych ADS-B.

**Poza MVP:** triangulacja, trenowanie własnego modelu, konta użytkowników, wysyłanie pełnego strumienia wideo przez MQTT, stuprocentowa identyfikacja lotów.

## Podział obowiązków

| Obszar | Właściciel | Zakres |
| --- | --- | --- |
| [camera-agent/](camera-agent/) | **Osoba 1 — kolega** | Python, OpenCV/YOLO, śledzenie obiektów, MQTT agent, komendy/status i REPLAY |
| [backend/](backend/) | **Osoba 2 — Kamil** | FastAPI, SQLite, odbiór MQTT, ADS-B, korelacja lotów, REST i WebSocket |
| [frontend/](frontend/) | **Osoba 2 — Kamil** | React, mapa, dashboard, historia i sterowanie |
| [shared/contracts/](shared/contracts/) | Obaj | Wersjonowane schematy wiadomości |
| [infrastructure/](infrastructure/) | Obaj | Mosquitto i uruchamianie środowiska |
| [test-data/](test-data/) | Obaj | Dane i scenariusze testowe (bez dużych filmów w Git) |
| [docs/](docs/) | Obaj | Dokumentacja i backlog |

## Architektura

~~~text
Camera Agent #1 --\
                  +-- MQTT Mosquitto <---> FastAPI <---> SQLite
Camera Agent #2 --/                         |  \
                                           |   +-- ADS-B API / replay snapshots
                                           +-- REST + WebSocket <---> React
~~~

Ten sam `camera-agent` uruchamia się na dwóch urządzeniach, z różnymi konfiguracjami. Broker, backend i frontend mogą działać na jednym laptopie, drugi agent na innym przez lokalne Wi-Fi.

## Pierwszy krok: MQTT

Przed implementacją ustalcie [protokół](docs/mqtt-protocol.md), schematy w `shared/contracts/` oraz przykłady w `shared/examples/`. Dzięki temu każda osoba może programować niezależnie na danych testowych.

Docker Compose uruchamia **tylko broker**, nie kompletną aplikację. Wymaga lokalnego pliku haseł:

~~~bash
docker run --rm -it -v "$(pwd)/infrastructure/mosquitto:/mosquitto/config" eclipse-mosquitto:2 mosquitto_passwd -c /mosquitto/config/passwords skywatch
docker compose up -d mqtt
docker compose ps
~~~

Instrukcja `-v "$(pwd)..."` jest przewidziana dla Linux/macOS; na Windowsie użyj poprawnego mapowania katalogu w Docker Desktop/PowerShell. Plik haseł i `.env` są ignorowane przez Git. Broker działa bez TLS, **tylko w zaufanej sieci lokalnej** — nie wystawiajcie portu 1883 do internetu.

## Dokumentacja
- [MVP i kryteria akceptacji](docs/mvp.md)
- [Architektura](docs/architecture.md)
- [Protokół MQTT](docs/mqtt-protocol.md)
- [Backlog z zadaniami](docs/backlog.md)
- [Plan testów i demo](docs/testing.md)
- [Git workflow](docs/workflow.md)

Zobacz też [GitHub Issues](../../issues) i pracuj na krótkich branchach z Pull Requestami.
