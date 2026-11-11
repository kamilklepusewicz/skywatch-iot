# Testowanie i demonstracja

W dniu prezentacji nie polegamy na tym, czy samolot przeleci przed kamerą.

## Tryby
- **LIVE:** prawdziwe kamery i bieżące ADS-B.
- **REPLAY:** dwa prawdziwe, wcześniej zarejestrowane nagrania i **zapisane wtedy** dane ADS-B; identyczny pipeline.
- **SIMULATED:** sztuczne wiadomości MQTT do testów logiki, nie dowód skuteczności Computer Vision.

## Scenariusze

| ID | Sytuacja | Oczekiwany rezultat |
| --- | --- | --- |
| T01 | Jeden samolot na MP4 | Detekcja + kandydaci albo jawny brak dopasowania |
| T02 | Puste niebo | Brak fałszywych detekcji w nagraniu |
| T03 | Ptak / obiekt nieznany | Brak wymuszonej identyfikacji lotu |
| T04 | Kilka potencjalnych lotów | Lista kandydatów / niepewność |
| T05 | Brak odpowiedzi ADS-B | Zapis obserwacji bez identyfikacji |
| T06 | Odłączenie kamery 2 | Offline dla 2; kamera 1 działa |
| T07 | Polecenie stop | Odbiór komendy, ACK i zatrzymanie analizy |
| T08 | Powtórzony MQTT QoS 1 | Brak drugiego rekordu w bazie |
| T09 | REPLAY 2 kamer | Zachowane oryginalne timestampy i jedna oś czasu ADS-B |

Potwierdzona identyfikacja lotu wymaga niezależnie ustalonej prawdy odniesienia (ground truth); system nie może oceniać sam siebie.

## Pokaz: 7–10 minut

1. Broker i dwie kamery online.
2. REPLAY nagrań i odpowiednich danych ADS-B.
3. Detekcje, kandydaci, historia na dashboardzie.
4. Komendy oraz symulowana awaria jednego agenta.
5. Ograniczenia dokładności i wyniki testów.

Dużych MP4 ani materiałów naruszających prywatność nie umieszczamy w repo.
