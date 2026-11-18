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

## Dwie kamery z podglądem na jednym komputerze z Windows

Uruchom Docker Desktop, stos Compose i oba agenty na tym samym komputerze.
Zainstaluj agenta i przygotuj model ONNX według [instrukcji Camera Agenta](camera-agent/README.md).
W każdym z dwóch terminali PowerShell aktywuj środowisko agenta. Ustaw dane
tego samego konta MQTT co w `.env.docker` przez interaktywny monit:

```powershell
$mqtt = Get-Credential -Message 'Podaj dane konta MQTT używanego przez SkyWatch'
$env:MQTT_HOST = '127.0.0.1'
$env:MQTT_PORT = '1883'
$env:MQTT_USERNAME = $mqtt.UserName
$env:MQTT_PASSWORD = $mqtt.GetNetworkCredential().Password
```

Z katalogu głównego uruchom poniższe polecenia, po jednym w każdym terminalu.
Indeksy `0` i `1` odpowiadają przykładowo kamerze wbudowanej i kamerze USB.
Jeśli Windows przypisał inne indeksy, zmień wartości `--camera` w poleceniach.

```powershell
skywatch-agent run --config camera-agent/examples/camera_1.toml --camera 0 --preview-port 8765
skywatch-agent run --config camera-agent/examples/camera_2.toml --camera 1 --preview-port 8766
```

Otwórz [localhost:5173](http://localhost:5173). Wystarczy panel z Compose.
Nginx przekazuje żądania `/preview/camera_1/` i `/preview/camera_2/`
do właściwych agentów przez `host.docker.internal` i przesyła MJPEG bez
buforowania. Panel i serwery podglądu nasłuchują lokalnie. Ta konfiguracja
korzysta z dostępu Docker Desktop do loopbacku hosta. Podgląd obejmuje agenty
uruchomione na tym komputerze. Agenty na innych komputerach mogą nadal
wysyłać obserwacje i odbierać polecenia przez MQTT.

### Sprawdzenie działania

1. Uruchom `docker compose up -d --build`, sprawdź `docker compose ps` i
   `docker compose exec frontend nginx -t`. Otwórz `/api/health`, `/api/cameras`,
   `/api/observations` i `/api/aircraft` pod adresem panelu. W narzędziach
   przeglądarki sprawdź połączenie `/ws` i czy konsola nie zgłasza błędów aplikacji.
2. W obu kartach wybierz **Uruchom LIVE**. Sprawdź ACK, oba obrazy i ramki przy
   wykryciu obiektu. Kliknij **Zatrzymaj** i sprawdź, czy obraz znika.
3. Wybierz scenariusz obsługiwany przez oba agenty i kliknij **Uruchom REPLAY**.
   Sprawdź podgląd, ACK i aktualizację historii bez odświeżania. Do próby bez
   kamery użyj `skywatch-agent generate-demo camera-agent/local/demo` w pustym
   katalogu docelowym. Uruchom agenty z wygenerowanymi plikami
   `camera-agent/local/demo/camera_1.toml` i `camera-agent/local/demo/camera_2.toml`
   oraz tymi samymi flagami `--preview-port`. W poleceniu importu z następnej
   sekcji użyj `/replay/agent-replay.json` i w panelu wybierz `synthetic-motion`.
4. Sprawdź mapę i historię obserwacji samolotów. Historia pokazuje znak
   wywoławczy lub adres ICAO kandydata ADS-B. Przy wielu kandydatach podaje
   ich liczbę i pierwszego z listy. Szczegóły pokazują wszystkich kandydatów.
   Dopasowanie wykorzystuje czas i odległość. Pewność detekcji opisuje ocenę
   YOLO, a tożsamość lotu wymaga niezależnego potwierdzenia. Dane demonstracyjne
   pozostają oznaczone jako syntetyczne. Przykład z kandydatem `SYNTH01` zawiera
   [test syntetycznego dopasowania](backend/DEVELOPMENT.md#b-syntetyczne-dopasowanie-samolotu).
5. Uruchom jednego agenta ponownie bez `--preview-port` i włącz analizę.
   Jego karta pokaże niedostępny podgląd, a druga kamera, historia i mapa
   pozostaną dostępne. Po wyłączeniu agenta karta pokaże stan offline.

Jeśli brakuje obrazu, porównaj status agenta na hoście z odpowiedzią Nginx.
Dla drugiej kamery użyj portu `8766` i ścieżki `camera_2`.

```powershell
Invoke-RestMethod http://127.0.0.1:8765/status.json
Invoke-RestMethod http://localhost:5173/preview/camera_1/status.json
docker compose exec frontend wget -T 3 -qO- http://host.docker.internal:8765/status.json
docker compose logs --tail 30 frontend
```

Jeśli odpowiada tylko pierwsze polecenie, sprawdź wersję Docker Desktop,
ustawienia VPN i zapory oraz wynik `wget` z kontenera. Zachowaj lokalne
nasłuchiwanie agentów. Jeśli oba statusy działają, sprawdź `mode`,
`captured_at` i `error`. Obraz pojawia się po odebraniu klatek w LIVE lub
REPLAY. Po chwilowym błędzie panel ponawia połączenie automatycznie.

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
