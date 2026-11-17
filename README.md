# SkyWatch IoT

Projekt zaliczeniowy z przedmiotu „Usługi i aplikacje Internetu Rzeczy”, realizowany przez dwie osoby.

SkyWatch IoT to rozproszony prototyp obserwacji nieba. Dwie instancje Camera Agenta wykrywają i śledzą obiekty w obrazie z kamer lub nagrań MP4. Panel pokazuje stan kamer, historię obserwacji i kandydatów z danych ADS-B. Z panelu można uruchomić LIVE lub REPLAY i zatrzymać analizę.

## Architektura

```text
Camera Agent 1 i 2 <-- MQTT --> Mosquitto <-- MQTT --> FastAPI <--> SQLite
Panel React <-- REST / WebSocket --> Nginx <-- REST / WebSocket --> FastAPI
```

Agenty publikują metadane obserwacji i statusy przez MQTT z QoS 1. Backend waliduje wiadomości według schematów kontraktu MQTT v1, deduplikuje obserwacje po `observation_id` i zapisuje je w SQLite. Wysyła też komendy i zapisuje potwierdzenia ACK od agentów. Panel pobiera dane przez REST i odświeża widoki po powiadomieniach WebSocket. Widok współrzędnych kamer i samolotów działa offline.

## Katalogi i podział pracy

| Katalog | Odpowiedzialność | Zakres |
| --- | --- | --- |
| [camera-agent/](camera-agent/) | Osoba 1 (Dawid), Computer Vision & IoT | Python, OpenCV, YOLO w formacie ONNX, śledzenie obiektów, źródła LIVE i REPLAY, MQTT (Paho) |
| [backend/](backend/) | Osoba 2 (Kamil), Flight Data & Web App | Python, FastAPI, SQLite, integracja MQTT i ADS-B, dopasowanie kandydatów, import REPLAY, REST i WebSocket |
| [frontend/](frontend/) | Osoba 2 (Kamil), Flight Data & Web App | React, TypeScript, Vite, status kamer i sterowanie, mapa i historia |
| [shared/](shared/) | Obaj | Schematy kontraktu MQTT i przykładowe wiadomości JSON |
| [infrastructure/](infrastructure/) | Obaj | Konfiguracja brokera Eclipse Mosquitto |
| [test-data/](test-data/) | Obaj | Zasady przechowywania danych i scenariuszy. Przykłady dla backendu są w [backend/fixtures/](backend/fixtures/). |
| [docs/](docs/) | Obaj | Dokumentacja, plan testów i backlog |

## Uruchomienie

### Pierwszy krok: MQTT

Do uruchomienia części serwerowej potrzebny jest Docker z Compose w wersji co najmniej 2.24. W Docker Desktop wybierz kontenery Linux. Skopiuj `docker.env.example` do `.env.docker`. Przygotuj lokalny plik `infrastructure/mosquitto/passwords` i wpisz dane tego samego konta jako `MQTT_USERNAME` i `MQTT_PASSWORD` w `.env.docker`. Tworzenie pliku haseł w jednorazowym kontenerze oraz użycie istniejącego konta opisuje [DOCKER.md](DOCKER.md#pierwsze-uruchomienie).

Broker wymaga hasła i działa bez TLS. Port TCP `1883` udostępniaj wyłącznie w zaufanej sieci lokalnej.

### Serwer i panel

Po jednorazowej konfiguracji MQTT uruchom to polecenie z katalogu głównego repozytorium.

```bash
docker compose up -d --build
```

Compose uruchamia Mosquitto, FastAPI i Nginx z panelem. FastAPI działa wewnątrz sieci Compose, a dane SQLite trafiają do wolumenu `backend-data`. Wejdź na [panel](http://localhost:5173) lub otwórz [dokumentację REST API](http://localhost:5173/docs).

### Camera Agenty

Agenta instalujesz osobno na każdym urządzeniu z Pythonem 3.11 lub nowszym. W terminalu agenta ustaw `MQTT_HOST` na adres IP hosta Docker w LAN, `MQTT_PORT=1883` oraz te same wartości `MQTT_USERNAME` i `MQTT_PASSWORD` co w `.env.docker`. Przykładowe konfiguracje wymagają lokalnego modelu ONNX. Instalację, przygotowanie modelu i wariant demonstracyjny bez wag opisuje [instrukcja Camera Agenta](camera-agent/README.md).

Pierwszego agenta uruchom z katalogu głównego repozytorium.

```bash
skywatch-agent run --config camera-agent/examples/camera_1.toml
```

Na drugim urządzeniu użyj `camera_2.toml`, żeby każdy agent miał własne `camera_id`. Agent czeka w trybie `idle` na komendę z panelu.

## LIVE, REPLAY i ADS-B

- LIVE korzysta z fizycznej kamery. Backend pobiera bieżące pozycje z adsb.lol przy włączonym ADS-B i ustawionych `ADSB_LATITUDE` oraz `ADSB_LONGITUDE`. Do dopasowania potrzebuje też współrzędnych kamery w `CAMERA_LOCATIONS`. Format ustawień opisuje [instrukcja backendu](backend/DEVELOPMENT.md#konfiguracja).
- REPLAY korzysta z lokalnych MP4. Agent wylicza `captured_at` z oryginalnego czasu początku nagrania i pozycji czasowej klatki. Wspólne `scenario_id` łączy nagrania z historycznymi migawkami ADS-B i współrzędnymi kamer importowanymi do bazy. Po przygotowaniu obrazów Dockera i plików scenariusza REPLAY działa bez internetu z lokalnym brokerem. Odpytywanie LIVE wyłączysz przez `ADSB_ENABLED=false`. [Import scenariusza w Dockerze](DOCKER.md#dane-i-tryby-pracy).

Dla obserwacji klasy `airplane` backend filtruje pozycje ADS-B według czasu klatki, wieku pozycji i odległości od kamery. Wynik to lista kandydatów albo informacja o braku dopasowania lub danych. Także pojedynczy kandydat wymaga niezależnego potwierdzenia.

## Testy i status MVP

- Testy Camera Agenta uruchom z katalogu głównego przez `python -m pytest camera-agent/tests -q` po instalacji zależności testowych. Testy integracyjne wymagają `mosquitto` i `mosquitto_passwd`.
- Testy backendu uruchom przez `python -m pytest -q` z katalogu `backend/`. Testy MQTT wymagają lokalnego `mosquitto`. [Instrukcja testów backendu](backend/DEVELOPMENT.md#testy).
- W katalogu `frontend/` uruchom `npm test`, `npm run typecheck`, `npm run lint` i `npm run build`. [Instrukcja pracy z frontendem](frontend/DEVELOPMENT.md).

Po uruchomieniu sprawdź `docker compose ps` oraz pola `mqtt_connected` i `mqtt_subscribed` w [health API](http://localhost:5173/api/health). Po podłączeniu agenta sprawdź jego status w panelu i wynik komendy `stop`.

MVP działa w środowisku testowym. W próbie stosu Docker z klientem testowym sprawdzono uwierzytelnienie MQTT, odbiór obserwacji, komendę z ACK, aktualizacje WebSocket i zachowanie danych po restarcie. W teście `synthetic_pair` zarówno obserwacja, jak i migawki ADS-B są syntetyczne. Demo `synthetic-motion` używa wygenerowanych MP4 i detektora ruchu, który zgłasza obiekty jako `unknown`.

Do sprawdzenia w terenie pozostały praca dwóch fizycznych kamer w docelowej sieci LAN, skuteczność detekcji na nagraniach samolotu i pustego nieba, działanie z bieżącym ADS-B oraz REPLAY dwóch prawdziwych nagrań z danymi ADS-B z tego samego okresu.

## Dokumentacja

- [Protokół MQTT](docs/mqtt-protocol.md) i [architektura](docs/architecture.md)
- [Kryteria akceptacji MVP](docs/mvp.md) i [plan testów i demo](docs/testing.md)
- [Backlog](docs/backlog.md) i [Git workflow](docs/workflow.md)
