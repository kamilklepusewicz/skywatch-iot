# Camera Agent — osoba 1 (Dawid / „kolega”)

Jedna aplikacja Python 3.11+ na dwa laptopy: LIVE/MP4, detekcja, tracking,
MQTT QoS 1, statusy/Last Will, komendy/ACK i historyczny REPLAY (CV-01–CV-05).
Backend, ADS-B, baza danych i frontend należą do Kamila.

Kod i testy techniczne są gotowe. **Testy skuteczności na prawdziwych nagraniach
samolotu/pustego nieba oraz uruchomienie na dwóch fizycznych laptopach pozostają do wykonania.**
Nagrania nie zostały dostarczone; generator demonstracyjny nie zastępuje tych testów.

## Instalacja

Wykonuj polecenia z głównego katalogu `skywatch-iot/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e './camera-agent[test]'
skywatch-agent --help
```

Na Debianie/Ubuntu utworzenie środowiska wymaga `python3-venv`.
Na Windowsie aktywuj `.venv\Scripts\Activate.ps1` w PowerShell.
Agent działa bez GUI i nie potrzebuje PyTorch w środowisku wykonawczym.

## Test bez kamery, modelu i brokera

```bash
# Jednorazowo: katalog docelowy musi być pusty lub nie istnieć.
skywatch-agent generate-demo camera-agent/local/demo
skywatch-agent evaluate --config camera-agent/local/demo/camera_1.toml \
  --scenario synthetic-motion --output camera-agent/local/motion-report.json --expect any
skywatch-agent evaluate --config camera-agent/local/demo/camera_2.toml \
  --scenario synthetic-motion --output camera-agent/local/camera-2-report.json --expect any
skywatch-agent evaluate --config camera-agent/local/demo/camera_1.toml \
  --scenario synthetic-empty --output camera-agent/local/empty-report.json --expect empty
```

Generator tworzy dwa MP4 z prostokątem w ruchu, pusty MP4, scenariusze i konfiguracje.
Każdy film ma 80 klatek (8 s). Dane mają `synthetic: true`, `scenario_id` z prefiksem
`synthetic-` oraz umowne daty; raport oznacza je jako `SIMULATED`.
Detektor ruchu publikuje wyłącznie `unknown`. Kontrakt MQTT v1 ma tylko tryby
`live`/`replay`, więc symulację rozpoznaje się po ID i metadanych scenariusza.

`evaluate` używa tego samego pipeline co aplikacja, bez MQTT. Raport zawiera
liczbę klatek, obserwacji i ścieżek, czasy oraz do 100 przykładów zdarzeń.
Kod wyjścia: `0` — spełnione oczekiwanie (lub nie podano oczekiwania),
`3` — niespełnione oczekiwanie, `2` — błąd konfiguracji/odczytu.

## Lokalny model YOLO

Obsługiwany format: **YOLOv8/YOLO11 detection, COCO 80 klas, ONNX FP32,
statyczne wejście 640×640, wyjście `[1,84,N]`, bez wbudowanego NMS**.
Agent publikuje `airplane` (COCO 4) i `bird` (COCO 14). Nie używaj modeli
segmentation, pose, OBB, innych układów klas ani modeli z innym formatem wyjścia.

Jednorazowy eksport z internetem, w osobnym środowisku:

```bash
python3 -m venv camera-agent/local/export-env
camera-agent/local/export-env/bin/python -m pip install torch torchvision \
  --index-url https://download.pytorch.org/whl/cpu
camera-agent/local/export-env/bin/python -m pip install 'ultralytics>=8.3,<9' \
  onnx onnxslim onnxruntime
camera-agent/local/export-env/bin/python camera-agent/scripts/prepare_model.py
```

Na Windowsie zamień `bin/python` na `Scripts/python.exe`.
Skrypt pobiera oficjalne `yolo11n.pt` i zapisuje `camera-agent/models/yolo11n.onnx`.
Skopiuj ONNX na drugi laptop. Agent nie pobiera modeli podczas pracy.
Przy innym `--image-size` ustaw tę samą wartość `image_size` w TOML.
Wagi, filmy i `local/` są ignorowane przez Git.
Źródła: [eksport Ultralytics](https://docs.ultralytics.com/modes/export/),
[modele YOLO11](https://docs.ultralytics.com/models/yolo11/).

## MQTT i LIVE

Uruchom istniejący broker z hasłem według [głównego README](../README.md#pierwszy-krok-mqtt).
Agent czyta zmienne środowiskowe, **nie ładuje automatycznie `.env`**.

```bash
export MQTT_HOST=127.0.0.1  # laptop B: adres LAN brokera
export MQTT_PORT=1883
export MQTT_USERNAME=skywatch
read -rsp 'Hasło MQTT: ' MQTT_PASSWORD
export MQTT_PASSWORD

# Oddzielne terminale/laptopy, różne camera_id:
skywatch-agent run --config camera-agent/examples/camera_1.toml
skywatch-agent run --config camera-agent/examples/camera_2.toml

# Albo natychmiastowe uruchomienie fizycznej kamery:
skywatch-agent run --config camera-agent/examples/camera_1.toml --mode live
```

Domyślnie agent jest w `idle` i czeka na komendę. `live_device = 0` oznacza pierwszą
kamerę; można użyć innego indeksu lub `/dev/videoN`. Zamknij programy zajmujące kamerę.
Ten sam `camera_id` w dwóch procesach powoduje konflikt identyfikatora MQTT.

Demo z brokerem, bez modelu (dwa terminale):

```bash
skywatch-agent run --config camera-agent/local/demo/camera_1.toml \
  --mode replay --scenario synthetic-motion
skywatch-agent run --config camera-agent/local/demo/camera_2.toml \
  --mode replay --scenario synthetic-motion
```

Koniec filmu przełącza agenta w `idle`; heartbeat i komendy pozostają aktywne.
`Ctrl+C`/SIGTERM zwalnia źródło i publikuje retained `online: false`.
Nagłą awarię obsługuje retained Last Will brokera.

## REPLAY prawdziwych nagrań

Skopiuj `examples/scenario.example.json` do własnego katalogu i uzupełnij:

- wspólne `scenario_id`, identyczne u obu agentów i w danych ADS-B Kamila;
- `cameras.camera_1.video` / `camera_2.video`: lokalne pliki nagrań;
- `captured_start`: **rzeczywisty czas pierwszej klatki** z `Z` albo offsetem;
- `synthetic: false` dla rzeczywistych nagrań.

Ścieżki w TOML są względem TOML; ścieżki scenariusza są względem jego JSON.
Dodaj scenariusz do `scenario_files`. Drugi laptop może mieć inne ścieżki,
ale musi zachować ID i czasy. Brak filmu drugiej kamery nie blokuje pierwszej.

`captured_at = captured_start + czas klatki w nagraniu`. Agent używa pozycji
czasowej OpenCV; przy braku rosnących PTS stosuje FPS (dla materiału CFR).
Dla VFR/dokładnej korekty dodaj w wpisie kamery
`"frame_offsets": "camera_1.timestamps.json"`. Ten plik zawiera tablicę
oryginalnych czasów klatek w sekundach, np. `[0.0, 0.041, 0.090]`:
początek 0, kolejne czasy ściśle rosnące, jeden wpis na każdą klatkę.

```bash
skywatch-agent run --config camera-agent/examples/camera_1.toml \
  --mode replay --scenario flight_001
skywatch-agent evaluate --config camera-agent/examples/camera_1.toml \
  --scenario flight_001 --output camera-agent/local/airplane-report.json --expect airplane
```

Przygotuj osobny scenariusz prawdziwego pustego nieba i oceń go przez `--expect empty`.
`replay_speed` zmienia tempo, nie `captured_at`. Historyczna oś czasu jest wspólna
nawet przy różnym czasie uruchomienia procesów. Kontrakt nie gwarantuje jednoczesnego
startu klatek względem zegara ściennego. Synchronizacja ADS-B należy do backendu.

## Komendy i integracja z Kamilem

Każda wiadomość przechodzi JSON Schema z kontrolą dat według [kontraktu v1](../docs/mqtt-protocol.md).
Pakiet zawiera identyczne kopie schematów; test porównuje je z `shared/contracts/`.
Wspólne schematy pozostają bez zmian.

| Kanał `skywatch/cameras/{id}/…` | QoS | Retain | Zawartość |
| --- | --- | --- | --- |
| `observations` | 1 | nie | UUID zdarzenia, stabilne lokalne `track_id` |
| `status` | 1 | tak | Heartbeat, zmiany trybu, offline/LWT |
| `commands` | 1 | nie | `start_live`, `start_replay`, `stop` |
| `ack` | 1 | nie | `command_id`, `accepted`, opis wyniku |

Test komendy bez backendu, w terminalu z tymi samymi zmiennymi MQTT:

```bash
python - <<'PY'
import json, os, uuid
from datetime import datetime, timezone
from paho.mqtt.publish import single
payload = {
    "schema_version": 1, "command_id": uuid.uuid4().hex, "camera_id": "camera_1",
    "issued_at": datetime.now(timezone.utc).isoformat(), "command": "stop",
}
single("skywatch/cameras/camera_1/commands", json.dumps(payload), qos=1, retain=False,
       hostname=os.environ.get("MQTT_HOST", "127.0.0.1"),
       port=int(os.environ.get("MQTT_PORT", "1883")),
       auth={"username": os.environ["MQTT_USERNAME"], "password": os.environ["MQTT_PASSWORD"]})
print(payload["command_id"])
PY
```

Przy `start_replay` dodaj znane agentowi `scenario_id`; komenda nie przyjmuje ścieżek plików.
Pozytywny ACK następuje po otwarciu źródła i odczycie pierwszej klatki
(dla `stop`: po zwolnieniu źródła). Błąd zmiany źródła daje negatywny ACK i zachowuje
poprzednie źródło. Późniejsza awaria detekcji/odczytu jest logowana i ustawia `idle`;
kontrakt v1 nie ma pola błędu w statusie.

Powtórzona komenda otrzymuje ten sam ACK bez ponownego wykonania (pamięć ostatnich
2048 komend w procesie). To samo ID z inną treścią jest odrzucane.
Agent odrzuca komendy starsze niż `command_max_age` (120 s), ponad 30 s z przyszłości
i dostarczone jako retained. Zsynchronizuj zegary laptopów. MQTT 3.1.1 nie oznacza
flagą retain bieżącej dostawy do istniejących subskrybentów; nadawca musi zawsze
publikować komendy z `retain=False`.

Paho automatycznie ponawia połączenie i subskrypcję. Kolejka publikacji QoS 1 jest
ograniczona (1000 wiadomości); przepełnienie jest logowane. To bufor w pamięci,
więc zakończenie procesu może utracić niewysłane obserwacje/ACK. Backend nadal
musi deduplikować `observation_id`. Last Will ma `mode: idle`, `scenario_id: null`
i czas przygotowania wiadomości; backend zapisuje też własny czas odbioru.

## Testy i ograniczenia

```bash
python -m pytest camera-agent/tests -q
ruff check camera-agent
ruff format --check camera-agent
```

Trzy testy integracyjne uruchamiają prywatny Mosquitto na losowym porcie localhost,
z tymczasowym hasłem, oraz dwa procesy agenta. Wymagają `mosquitto` i
`mosquitto_passwd` w PATH (albo `MOSQUITTO_BIN` / `MOSQUITTO_PASSWD_BIN`).
Bez nich pytest jawnie je pomija. Testowy broker nie zmienia infrastruktury projektu.
Sprawdzane są restart brokera, ponowna subskrypcja, odrzucenie złego hasła,
QoS 1, duplikaty komend, stop, retained LWT i niezależność agentów.
Osobny test wczytuje lokalny model YOLO i wykonuje inferencję; jest pomijany,
jeżeli nie przygotowano wag. Test ten nie mierzy skuteczności na prawdziwym niebie.

- YOLO może pomijać małe/odległe samoloty, szczególnie na tle chmur lub przy rozmyciu.
  Próg confidence i rozdzielczość trzeba ocenić na rzeczywistych danych.
- Tracker może zamienić ID przy skrzyżowaniu podobnych obiektów lub długiej utracie
  widoczności. `track_id` nie jest identyfikatorem lotu.
- Detekcja ruchu wymaga nieruchomej kamery i rozgrzewki. Reaguje też na chmury,
  drgania i światło. Jej confidence to wypełnienie maski ruchu, nie pewność klasy.
- `min_hits = 3` odfiltrowuje krótkie detekcje; `observation_interval = 0.5`
  ogranicza publikacje na ścieżkę według czasu klatki.
- REPLAY przetwarza każdą klatkę. Na wolnym CPU zwalnia, zachowując timestampy.
  Komendy są obsługiwane między klatkami.

### Odbiór CV-01–CV-05

| Zadanie | Dostarczone | Pozostały test manualny |
| --- | --- | --- |
| CV-01 | LIVE/MP4, konfiguracja, błędy urządzenia | Kamera na dwóch laptopach |
| CV-02 | YOLO ONNX, ruch, raport `evaluate` | Samolot i puste niebo na prawdziwych MP4 |
| CV-03 | Tracker, UUID, walidacja, QoS 1 | Odbiór przez backend po implementacji Kamila |
| CV-04 | Komendy/ACK, deduplikacja, status, LWT, reconnect | Docelowa sieć LAN |
| CV-05 | Dwa agenty, scenariusze, historyczne czasy, VFR | Dwa prawdziwe filmy i oś czasu ADS-B |

Nie zaznaczamy akceptacji testów manualnych przed ich faktycznym wykonaniem.
