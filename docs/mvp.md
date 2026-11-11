# MVP — kryteria akceptacji

- [ ] Dwa fizyczne urządzenia uruchamiają identyczną aplikację agenta, z innym `camera_id`.
- [ ] LIVE i REPLAY uruchamiają wspólny pipeline detekcji.
- [ ] Na co najmniej jednym realnym MP4 wykryty zostaje samolot; na zestawie pustego nieba nie ma fałszywego alarmu.
- [ ] Status, obserwacje, komendy i ACK działają dwukierunkowo przez MQTT.
- [ ] FastAPI zapisuje i deduplikuje obserwacje w SQLite; REST/WebSocket je udostępnia.
- [ ] ADS-B klient obsługuje pobieranie, cache, timeouty, limity i brak sieci.
- [ ] Korelacja wskazuje listę kandydatów **lub brak dopasowania**, bez wymuszonego wyniku.
- [ ] Dashboard pokazuje 2 kamery, historię, kandydatów i zdalne sterowanie.
- [ ] REPLAY działa offline, z historycznymi filmami i migawkami ADS-B o wspólnej osi czasu.
- [ ] Wyłączenie agenta 2 nie zatrzymuje agenta 1 i jest oznaczone jako offline.

Poza MVP: triangulacja, trenowanie własnego modelu, konta użytkowników i idealna identyfikacja lotu.

**Rzetelność:** wyniki LIVE, REPLAY i testów syntetycznych muszą być jawnie rozróżnione.
