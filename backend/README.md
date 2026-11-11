# Backend — osoba 2 (Kamil)

FastAPI, MQTT, SQLite, dane ADS-B, korelacja i REST/WebSocket.

## Zakres
- Odbiór, walidacja i deduplikacja obserwacji na podstawie `observation_id`.
- Historia w SQLite i API do kamer, obserwacji, lotów i komend.
- Integracja adsb.lol: timeout, cache, limity, obsługa błędów.
- W REPLAY zapisane snapshoty ADS-B zsynchronizowane z `captured_at`, a nie bieżące zapytania.
- Dopasowywanie kandydatów na podstawie czasu/obszaru, bez deklarowania pewnej identyfikacji bez kalibracji.
- WebSocket dla aktualizacji na żywo; wysyłanie poleceń i odczyt ACK.

Planowana struktura:
```text
backend/
  app/
    main.py
    api/
    integrations/adsb.py
    services/matching.py
    services/replay.py
    mqtt/subscriber.py
    models.py
    schemas.py
    database.py
  tests/
  pyproject.toml
```
**Granica odpowiedzialności:** przetwarzamy metadane, nie klatki wideo. [Kontrakt MQTT](../docs/mqtt-protocol.md).
