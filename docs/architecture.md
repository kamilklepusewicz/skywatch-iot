# Architektura SkyWatch IoT

## Węzły fizyczne

- **Laptop A:** `camera-agent` (camera_1), opcjonalnie Mosquitto, FastAPI i React.
- **Laptop B:** `camera-agent` (camera_2), łączy się z brokerem przez lokalne Wi-Fi.
- Agenty są **dwiema instancjami tego samego kodu** z oddzielnymi plikami konfiguracji, a nie dwiema odrębnymi aplikacjami.

## Przepływ

~~~mermaid
flowchart LR
  CA1[Camera Agent 1] <-->|MQTT| M[Mosquitto]
  CA2[Camera Agent 2] <-->|MQTT| M
  M <-->|obserwacje, status, komendy| B[FastAPI]
  B <--> DB[(SQLite)]
  B <-->|LIVE / zapisane snapshoty| A[ADS-B]
  B <-->|REST + WebSocket| F[React]
~~~

## Granice odpowiedzialności

- **Agent (osoba 1):** obraz, detekcja, lokalny tracker, źródło klatek, timestampy, MQTT i ACK.
- **Backend (osoba 2):** walidacja, deduplikacja, historia, ADS-B, dopasowanie kandydatów, REST/WebSocket i komendy.
- **Frontend (osoba 2):** UI, mapa, historia, sterowanie; brak bezpośredniego dostępu do Mosquitto.
- **Shared (obaj):** formaty JSON + wersje protokołu i testy kontraktowe.

## Identyfikacja lotów

W MVP algorytm wyznacza **kandydatów**, ograniczonych czasem i przybliżoną lokalizacją obserwacji. Nie wolno uznawać jedynego pobliskiego samolotu za na pewno zidentyfikowany, jeśli nie znamy dokładnej orientacji, pola widzenia i położenia kamery.

Rozszerzenie: kalibracja kamer, przewidywany azymut/elewacja lotu oraz porównanie z pozycją obiektu w obrazie.

## REPLAY

W trybie REPLAY oba agenty odczytują wcześniej nagrane materiały z oryginalnymi timestampami. Backend dopasowuje historyczne migawki ADS-B do `captured_at`; **nie używa bieżących odpowiedzi API**.

## Bezpieczeństwo

Dane MQTT są metadanymi (nigdy pełnym strumieniem obrazu). Broker Mosquitto wymaga hasła, ale szkielet nie dostarcza szyfrowania TLS; wyłącznie lokalna zaufana sieć, bez przekierowywania 1883 do internetu.
