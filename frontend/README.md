# Frontend — osoba 2 (Kamil)

React + TypeScript + Vite. **Aplikacja nie jest jeszcze wygenerowana**; utwórz ją podczas implementacji.

MVP:
- status dwóch kamer (online/offline, LIVE/REPLAY);
- obserwacje i historia zdarzeń;
- kandydaci ADS-B z wyraźną informacją o niepewności;
- sterowanie `start_live`, `start_replay`, `stop` i status ACK;
- prosta mapa pobliskich samolotów (np. Leaflet);
- REST do danych początkowych, WebSocket do aktualizacji na żywo.

Frontend komunikuje się z FastAPI, a nie bezpośrednio z MQTT. Nie wysyłajcie wideo przez MQTT.
