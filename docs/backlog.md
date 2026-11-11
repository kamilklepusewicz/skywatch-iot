# Backlog SkyWatch IoT

Źródło planu pracy dla **dwóch osób**. Poszczególne zadania są także prowadzone jako [GitHub Issues](https://github.com/kamilklepusewicz/skywatch-iot/issues).

**Podział:** Osoba 1 = Computer Vision & IoT (kolega). Osoba 2 = Flight Data & Web App (Kamil).
**Priorytety:** P0 = konieczne do MVP, P1 = kolejny etap / element wizualny.
**Status na starcie:** wszystkie zadania otwarte; infrastruktura i schematy są tylko szkieletem, nie działającą aplikacją.

| ID | Priorytet | Właściciel | Zadanie | Ukończone, gdy... |
| --- | --- | --- | --- | --- |
| SH-01 | P0 | Wspólnie | Ustalić kontrakty MQTT v1 | Schematy, tematy, testowe wiadomości oraz zasady zmian zatwierdzone przez obie osoby |
| SH-02 | P0 | Wspólnie | Uruchomić broker Mosquitto w LAN | Oba laptopy łączą się z uwierzytelnieniem, pub/sub działa w obie strony |
| CV-01 | P0 | Osoba 1 | LIVE i MP4 w camera-agent | Jedna aplikacja czyta kamerę lub MP4 z konfigurowalnym camera_id |
| CV-02 | P0 | Osoba 1 | Detekcja obiektów na niebie | Detekcja na co najmniej jednym nagraniu samolotu, test pustego nieba |
| CV-03 | P0 | Osoba 1 | Tracking i MQTT observations | Stabilne ID obiektu; walidowane zdarzenia MQTT i test QoS 1 |
| CV-04 | P0 | Osoba 1 | Statusy, komendy i ACK | start_live, start_replay, stop i poprawne odpowiedzi/Last Will |
| CV-05 | P0 | Osoba 1 | REPLAY dla dwóch agentów | Dwa filmy, wspólne scenario_id i historyczny captured_at |
| WEB-01 | P0 | Osoba 2 | FastAPI + SQLite | Obserwacje zapisane, zwalidowane i deduplikowane |
| WEB-02 | P0 | Osoba 2 | MQTT subscriber + control | Odbiór detekcji/statusów i publikacja komend z obsługą ACK |
| WEB-03 | P0 | Osoba 2 | ADS-B klient i snapshoty | Pobieranie danych, cache, obsługa limitów i historyczny REPLAY |
| WEB-04 | P0 | Osoba 2 | Korelacja z lotami | Kandydaci na podstawie czasu/obszaru albo brak dopasowania, bez fałszywej pewności |
| WEB-05 | P0 | Osoba 2 | REST i WebSocket | Historia, kamery i zdarzenia aktualizowane bez odświeżania |
| WEB-06 | P1 | Osoba 2 | Dashboard React i mapa | Statusy 2 kamer, historia, kandydaci, sterowanie, mapa |
| SH-03 | P0 | Wspólnie | Testy i demo LIVE/REPLAY | Scenariusze T01–T09 sprawdzone na 2 urządzeniach, prezentacja nie wymaga samolotu na żywo |

## Kolejność i zależności

1. **Najpierw SH-01 i SH-02** — bez wspólnego kontraktu protokół będzie się rozjeżdżać.
2. **Równolegle:** CV-01/02 oraz WEB-01/03. Backend pracuje z przykładowymi eventami, nawet gdy detektor nie jest gotowy.
3. **Integracja:** CV-03/04 i WEB-02/05; jeden rzeczywisty event z kamery dociera do dashboardu.
4. **Identyfikacja i REPLAY:** CV-05 i WEB-04; dane ADS-B muszą mieć tę samą oś czasu co wideo.
5. **Prezentacja:** WEB-06 i SH-03, w tym test offline i awarii jednego agenta.

## Definition of Done dla Issue

- Zmiana jest na osobnym branchu i ma opisany PR.
- Dodano odpowiednie testy (lub udokumentowano manualny test).
- Interfejsy między modułami pozostają zgodne z kontraktem.
- PR został sprawdzony przez drugą osobę.
- README/dokumentacja są aktualne, jeżeli zmieniło się uruchamianie albo API.

**Nie wrzucajcie dużych filmów, haseł ani wag modeli do historii Git.**
