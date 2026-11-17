# SkyWatch IoT w Docker Compose

## Pierwsze uruchomienie

Uruchom Docker Desktop z kontenerami Linux i Compose w wersji co najmniej 2.24.
W PowerShellu, z katalogu głównego repozytorium, przygotuj jednorazowo
konfigurację brokera i backendu. Polecenie z `mosquitto_passwd -c` wykonaj
tylko wtedy, gdy `infrastructure/mosquitto/passwords` jeszcze nie istnieje.

```powershell
Copy-Item docker.env.example .env.docker
$mqttConfig = (Resolve-Path '.\infrastructure\mosquitto').Path
docker run --rm -it --mount "type=bind,source=$mqttConfig,target=/mosquitto/config" eclipse-mosquitto:2 sh -ec 'mosquitto_passwd -c /mosquitto/config/passwords skywatch && chown mosquitto:mosquitto /mosquitto/config/passwords'
```

Podaj hasło w interaktywnym monicie. W `.env.docker` zapisz tę samą nazwę
użytkownika i hasło jako `MQTT_USERNAME` i `MQTT_PASSWORD`. Przy istniejącym
pliku użyj danych istniejącego konta. Jeśli właścicielem pliku jest `root`,
uruchom w tym samym kontenerze z montowaniem samo polecenie `chown` z przykładu.
Hasło z `$` lub `#` wpisz w pojedynczych apostrofach. Git ignoruje oba lokalne pliki.

Po tej konfiguracji cały serwer uruchamia się jednym poleceniem:

```powershell
docker compose up -d --build
```

- Panel działa lokalnie pod [localhost:5173](http://localhost:5173).
  Nginx przekazuje `/api`, `/ws` i [dokumentację API](http://localhost:5173/docs)
  do FastAPI na wewnętrznym `backend:8000`.
- Backend łączy się z brokerem pod `mqtt:1883`. Camera Agenty uruchamiaj
  na ich urządzeniach. Podaj im adres IP hosta Docker w LAN, port TCP `1883`
  i te same dane logowania. W zaporze ogranicz dostęp do zaufanej podsieci LAN.
  Pozostaw port `1883` bez przekierowania na routerze.
- `docker compose config --quiet` sprawdza konfigurację bez wyświetlania haseł.
  `docker compose ps` i `docker compose logs backend mqtt` pokazują stan usług.
  W [health API](http://localhost:5173/api/health) pola `mqtt_connected`
  i `mqtt_subscribed` potwierdzają osobno stan połączenia i subskrypcji.

## Dane i tryby pracy

SQLite zapisuje dane w wolumenie `backend-data` pod `/data/skywatch.sqlite3`.
Wolumen pozostaje po restarcie, przebudowie i `docker compose down`.
Jeśli ustawiasz `DATABASE_PATH` lub `DATABASE_URL`, wybierz jedną zmienną
i wskaż plik w `/data`. Bazy deweloperskie na hoście pozostają odrębne.

Dla LIVE podaj w `.env.docker` rzeczywiste `ADSB_LATITUDE`,
`ADSB_LONGITUDE` oraz `CAMERA_LOCATIONS`. Pełna lista ustawień, w tym
format lokalizacji i okna dopasowania, jest w [instrukcji backendu](backend/DEVELOPMENT.md#konfiguracja).

Dla REPLAY offline ustaw `ADSB_ENABLED=false`. Po zmianie `.env.docker`
uruchom `docker compose up -d backend`, aby zastosować ustawienia.
Poniższe polecenie importuje repozytoryjny scenariusz syntetyczny do tego
samego wolumenu SQLite:

```powershell
$scenarios = (Resolve-Path '.\backend\fixtures').Path
docker compose run --rm --no-deps --volume "${scenarios}:/replay:ro" backend python -m app.replay /replay/synthetic-replay.json
```

Dla własnego scenariusza wskaż katalog z manifestami i zamień nazwę pliku.
Opcja `--agent-manifest /replay/agent.json` sprawdza zgodność z manifestem
agenta. Zachowaj wspólne ID scenariusza i oryginalne czasy nagrań.
Po imporcie odśwież panel.
