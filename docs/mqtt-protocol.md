# MQTT — kontrakt v1

Protokół między `camera-agent` (osoba 1) i `backend` (osoba 2). **Każda zmiana wymaga przeglądu obu osób.**

## Tematy

| Topic | Publikuje | Odbiera | QoS | Retain |
| --- | --- | --- | --- | --- |
| `skywatch/cameras/{camera_id}/observations` | Agent | Backend | 1 | nie |
| `skywatch/cameras/{camera_id}/status` | Agent / broker LWT | Backend | 1 | tak |
| `skywatch/cameras/{camera_id}/commands` | Backend | Agent | 1 | nie |
| `skywatch/cameras/{camera_id}/ack` | Agent | Backend | 1 | nie |

`camera_id` to np. `camera_1`, `camera_2`. Wiadomości to JSON, `schema_version: 1`; schematy w [shared/contracts](../shared/contracts/), przykłady w [shared/examples](../shared/examples/).

## Semantyka

- `observation_id` i `command_id` muszą być unikalne; MQTT QoS 1 może dostarczyć wiadomość ponownie, backend musi deduplikować.
- `captured_at` to czas **oryginalnej klatki** (UTC). W REPLAY musi odpowiadać scenariuszowi i historycznym danym ADS-B. `scenario_id` łączy nagranie, obserwacje i snapshoty.
- `bbox` = [x, y, width, height], znormalizowane do 0–1 względem klatki, lewy górny róg jako (0,0).
- `confidence` to wynik detektora obiektów, a nie pewność identyfikacji konkretnego lotu.
- ACK odnosi się do `command_id`: UI pokazuje pending aż do ACK lub timeout.
- Status jest retained; agent publikuje `online: true` i konfiguruje retained Last Will `online: false`. Timestamp LWT nie jest dokładną chwilą awarii — backend osobno zapisuje czas otrzymania.
- **Nie** ustawiajcie retain dla komend. Stare polecenie nie może uruchomić się samo po restarcie agenta.

## Obsługiwane polecenia

- `start_live` — przetwarzaj obraz fizycznej kamery.
- `start_replay` z `scenario_id` — odtwórz lokalny MP4 z danymi scenariusza.
- `stop` — zatrzymaj analizę.

## Minimalny handshake

1. Broker Mosquitto z hasłem osiągalny z obydwu laptopów.
2. Agent 1 publikuje status i przykładową obserwację; backend je odbiera.
3. Backend wysyła `stop` z `command_id`, agent odsyła ACK.
4. Powtórz to samo dla agenta 2 z odrębnym `camera_id`.
5. Wyłącz agenta 2 i zweryfikuj retained LWT oraz niezależność agenta 1.
