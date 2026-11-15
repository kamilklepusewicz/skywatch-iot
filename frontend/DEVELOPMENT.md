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
Po zbudowaniu frontend wymaga serwera statycznego z proxy tych samych dwóch
ścieżek. Lokalnie można użyć `npm.cmd run preview`, gdy port 5173 jest wolny.

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
