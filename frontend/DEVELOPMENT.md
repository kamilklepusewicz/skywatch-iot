# Uruchomienie panelu

Wymagany jest Node.js 20.19+ lub 22.12+. Uruchom [backend](../backend/DEVELOPMENT.md)
na porcie 8000, a następnie w drugiej konsoli w katalogu głównym:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Otwórz [127.0.0.1:5173](http://127.0.0.1:5173). Vite przesyła `/api` i `/ws`
do backendu. Zmienna `SKYWATCH_BACKEND_URL` pozwala wskazać inny adres upstream.
Lokalnie można też użyć `npm.cmd run build` i `npm.cmd run preview`, gdy port
5173 jest wolny.

## Podgląd kamer w panelu

Karty kamer pokazują obraz z lokalnych agentów wraz z ramkami detekcji.
Uruchom agenta `camera_1` z `--preview-port 8765`, a `camera_2` z
`--preview-port 8766` (zobacz [instrukcję agenta](../camera-agent/README.md)).
Każdy agent musi używać innej kamery. Kliknij **Uruchom LIVE** w karcie kamery;
**Zatrzymaj** usuwa obraz z podglądu, a **REPLAY** pokazuje wybrane nagranie.
Brak połączenia lub klatek jest sygnalizowany w miejscu obrazu.

Vite w trybach `dev` i `preview` przekazuje `/preview/camera_1/` i
`/preview/camera_2/` do agentów na portach 8765 i 8766. Adresy upstream można
zmienić przez `SKYWATCH_PREVIEW_CAMERA_1_URL` i
`SKYWATCH_PREVIEW_CAMERA_2_URL` przed uruchomieniem Vite. Agent domyślnie
nasłuchuje tylko na loopback; przy pracy na innym komputerze można udostępnić
go serwerowi panelu przez tunel SSH. Obraz nie przechodzi przez MQTT.

Panel w Docker Compose obsługuje te same ścieżki przez Nginx. Instrukcję
uruchomienia i sprawdzenia podglądu obu kamer na Windows zawiera
[instrukcja Docker Compose](../DOCKER.md#dwie-kamery-z-podglądem-na-jednym-komputerze-z-windows).

## Historia i mapa

Panel wyświetla czas w UTC. Po otwarciu obserwacji mapa pokazuje pozycje jej
kandydatów. Zaznaczenie punktu pokazuje czas pozycji i jego snapshotu.
Po zamknięciu szczegółów można wrócić do widoku wybranego źródła ADS-B.
Widok współrzędnych działa offline. Kamery REPLAY są rysowane na podstawie
lokalizacji podanych w manifeście scenariusza.

Historia obsługuje filtr scenariusza oraz przejście do starszych danych według
kursora ostatniej pozycji na stronie. Gdy WebSocket jest rozłączony, panel
oznacza historię i mapę jako potencjalnie nieaktualne, a stan kamer i komend
odświeża przez REST co 5 sekund. Pełna synchronizacja następuje po ponownym
połączeniu.

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```
