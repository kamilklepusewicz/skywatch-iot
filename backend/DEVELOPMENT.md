# Uruchomienie backendu

Python 3.11 lub nowszy. Z katalogu głównego repozytorium w PowerShellu:

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
$env:MQTT_USERNAME = 'skywatch'
$env:MQTT_PASSWORD = Read-Host 'Hasło istniejącego brokera'
$env:MQTT_HOST = '127.0.0.1'
$env:MQTT_PORT = '1883'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Na Linuxie i macOS ścieżka do Pythona środowiska to `.venv/bin/python`.
Do uruchomienia samego API i odczytu danych historycznych ustaw `MQTT_ENABLED=false`.
Do prezentacji z Camera Agentami potrzebny jest działający broker. Agenty oraz
backend muszą używać tego samego brokera. Instrukcje konfiguracji istniejącego
brokera są w [README repozytorium](../README.md). API z komendami jest przeznaczone
do lokalnej prezentacji w zaufanym środowisku. Vite domyślnie używa portu 5173,
a do uruchomienia na innym originie ustaw `WEB_ORIGINS` jako tablicę JSON.

## Konfiguracja

| Zmienne | Znaczenie |
| --- | --- |
| `DATABASE_PATH`, `DATABASE_URL` | Domyślnie `backend/skywatch.sqlite3`. Ścieżka ma pierwszeństwo przed adresem `sqlite:///...`. Względne ścieżki są liczone od katalogu roboczego. |
| `MQTT_ENABLED`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD` | Połączenie MQTT 3.1.1. Pusta nazwa użytkownika oznacza połączenie anonimowe. |
| `CAMERA_IDS`, `CAMERA_LOCATIONS` | Domyślne identyfikatory to `["camera_1","camera_2"]`. Lokalizacje jako obiekt JSON, gdzie kluczem jest ID kamery, a wartością obiekt z polami `latitude` i `longitude`. |
| `HEARTBEAT_TIMEOUT_SECONDS`, `COMMAND_TIMEOUT_SECONDS` | Domyślnie 45 s i 15 s. Ustaw próg heartbeat powyżej okresu publikacji agenta. |
| `ADSB_ENABLED`, `ADSB_LATITUDE`, `ADSB_LONGITUDE`, `ADSB_RADIUS_NM` | Odpytywanie LIVE zaczyna się po podaniu obu współrzędnych. Domyślny promień zapytania to 30 NM. Obszar powinien obejmować obie kamery i ich promienie dopasowania. |
| `ADSB_POLL_SECONDS`, `ADSB_TIMEOUT_SECONDS`, `ADSB_API_KEY` | Domyślnie 180 s i 8 s. Bez klucza backend wymusza interwał co najmniej 180 s. Z kluczem dostosuj interwał do limitu planu. |
| `CLOCK_WARNING_SECONDS` | Domyślnie 30 s. Próg ostrzeżenia dla bezwzględnej różnicy czasu. |
| `MATCH_RADIUS_KM`, `MATCH_WINDOW_SECONDS`, `ADSB_MAX_POSITION_AGE_SECONDS`, `ADSB_LIVE_RETENTION_HOURS` | Domyślnie 20 km, ±35 s od klatki, wiek pozycji ≤30 s w snapshocie i 48 h retencji snapshotów LIVE. |

Backend wczytuje również `.env` z katalogu roboczego. Dokumentacja interfejsu
jest dostępna pod [localhost:8000/docs](http://127.0.0.1:8000/docs). Dane LIVE
pochodzą z adsb.lol i podlegają ODbL 1.0. [Dokumentacja i limity ADS-B](https://www.adsb.lol/docs/open-data/api).

## Czas i świeżość ADS-B LIVE

`ADSB_LATITUDE` i `ADSB_LONGITUDE` wyznaczają obszar zapytania. Odległość do samolotu
jest liczona od fizycznej lokalizacji kamery z `CAMERA_LOCATIONS`. W REPLAY używane
są współrzędne tej kamery ze scenariusza. Brak współrzędnych daje
`camera_location_missing`.

API rozróżnia czas klatki, odbioru MQTT, wygenerowania snapshotu (`source_at`),
pozycji (`source_at - seen_pos`) i pobrania (`retrieved_at`). Ustawienia czasu i
różnica pobranie − źródło są dostępne pod `/api/health`. Szczegóły obserwacji LIVE
pokazują różnicę odbiór − klatka. Duża różnica może wynikać z zegarów, kolejki,
sieci lub opóźnionego źródła. Porównaj zegary UTC obu kamer i backendu oraz
sprawdź synchronizację NTP. Obliczenia korzystają z oryginalnych znaczników.

Minimum 180 s bez klucza daje najwyżej około 480 zapytań na dobę dla jednego
procesu. Inni klienci tego samego IP również zużywają limit. Przy oknie ±35 s
nawet poprawnie działające odpytywanie zostawia luki. Status `stale` oznacza
dane poza oknem, `unavailable` oznacza brak danych potrzebnych do oceny.
Jeżeli potrzeba gęstszych snapshotów, użyj źródła lub planu o odpowiednim
budżecie i skonfiguruj `ADSB_API_KEY` oraz `ADSB_POLL_SECONDS`.

## REPLAY offline

W terminalu backendu ustaw `ADSB_ENABLED=false` i pozostaw MQTT włączone.
Import i FastAPI powinny używać tego samego `DATABASE_PATH`. Do demonstracji
możesz wskazać nowy plik bazy w katalogu tymczasowym.

### A. Integracja dwóch Camera Agentów

W środowisku Camera Agenta wygeneruj przykładowe nagrania:

```powershell
$demo = Join-Path $env:TEMP ('skywatch-demo-' + [guid]::NewGuid())
skywatch-agent generate-demo $demo
```

Z katalogu `backend`, używając tego samego `$demo`:

```powershell
.\.venv\Scripts\python.exe -m app.replay fixtures/agent-replay.json --agent-manifest "$demo/synthetic-motion.json"
```

Scenariusz `synthetic-motion` ma start `2026-01-01T12:00:00.000Z` dla
`camera_1` i `2026-01-01T12:00:00.200Z` dla `camera_2`. Opcja
`--agent-manifest` sprawdza identyfikatory, oznaczenie danych syntetycznych
oraz zadeklarowane czasy startu. Uruchom poniższe komendy po jednej w każdym
terminalu Camera Agenta, z tym samym brokerem i ścieżką do katalogu `$demo`:

```powershell
skywatch-agent run --config "$demo/camera_1.toml"
skywatch-agent run --config "$demo/camera_2.toml"
```

W panelu wybierz `synthetic-motion` dla obu kamer i kliknij `Uruchom REPLAY`.
Agenty publikują rzeczywiste wyniki pracy detektora ruchu na wygenerowanych
klatkach. Klasa `unknown` sprawdza komunikację, zapis i odświeżanie panelu.
Dopasowanie ADS-B dla tej klasy jest pomijane.

### B. Syntetyczne dopasowanie samolotu

Z katalogu `backend` zaimportuj `synthetic_pair` i opublikuj oznaczoną
obserwację testową przy uruchomionym backendzie. Przykład używa narzędzia
`mosquitto_pub` z pakietu Mosquitto i zmiennych brokera z sekcji uruchomienia.

```powershell
.\.venv\Scripts\python.exe -m app.replay fixtures/synthetic-replay.json
mosquitto_pub -h $env:MQTT_HOST -p $env:MQTT_PORT -u $env:MQTT_USERNAME -P $env:MQTT_PASSWORD -q 1 -t skywatch/cameras/camera_1/observations -f fixtures/synthetic-observation.json
```

Otwórz obserwację ze scenariusza `synthetic_pair` w historii. Klatka z
`2026-01-02T12:00:00Z` daje kandydata `SYNTH01` na mapie. Obie strony tego
przykładu są syntetyczne. Ponowna publikacja tego samego ID podlega deduplikacji.

### Rzeczywiste materiały

Dla wspólnego `scenario_id` przygotuj nagrania MP4 i ich oryginalne czasy
startu, model ONNX używany przez agenty, współrzędne każdej kamery i snapshoty
z epoki nagrań. Pole `cameras` w manifeście backendu przypisuje identyfikatorom
współrzędne lub `null`. Opcjonalny `origin` jest środkiem widoku mapy.
Pole `camera_starts` pozwala sprawdzić czasy przez `--agent-manifest`.

Wpis w `snapshots` zawiera `response` z `now` w sekundach lub milisekundach
epoki Unix oraz tablicą `ac`. Dla plików readsb zmień klucz `aircraft` na `ac`.
Podaj `retrieved_at` z offsetem, jeśli znasz czas pobrania. Import tego samego
ID zastępuje metadane i snapshoty w jednej transakcji.

## Komendy i zajęta baza

Broker i kamera mają osobne stany. Status offline, w tym Last Will, działa
od chwili odbioru. Przy braku potwierdzonej subskrypcji lub pełnej kolejce
wyjściowej komenda dostaje `publish_failed`. Gdy Paho zgłasza utratę połączenia
podczas próby publikacji, komenda może pozostać w kolejce QoS 1 i dostaje
`delivery_uncertain`. Timeout oznacza brak ACK w terminie. Pierwszy poprawny
ACK nadal aktualizuje wynik i otrzymuje flagę `late`. Starsze zapisane
`publish_failed` mogą pochodzić z wcześniejszej, niejednoznacznej obsługi
Paho.

Zapis podczas blokady SQLite jest odraczany z ograniczonymi ponowieniami.
Odczyty działają przez WAL. Gdy początkowy zapis komendy jest zablokowany, API
zwraca HTTP 503 przed publikacją. Przy długotrwałej blokadzie część danych może
zostać pominięta po wyczerpaniu ponowień lub kolejki. Logi `sqlite_busy` i
`mqtt_persistence_failed` wskazują operację. Starsze obserwacje z uszkodzoną
ramką pozostają w bazie i są pomijane w historii.

## Testy

Z katalogu `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Test Mosquitto uruchamia tymczasowy broker na interfejsie loopback, jeśli
`mosquitto` jest w `PATH` lub `MOSQUITTO_BIN` wskazuje plik wykonywalny.
Reszta testów nie wymaga brokera, kamery ani publicznego ADS-B.
