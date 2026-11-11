# Materiały testowe

W repozytorium trzymamy tylko lekkie metadane, fixtures JSON i scenariusze. **Nie commitujemy dużych MP4, wag modeli ani prywatnych nagrań.**

Każdy scenariusz REPLAY powinien dokumentować:
- wspólne `scenario_id` i lokalne pliki `camera_1.mp4`, `camera_2.mp4`;
- oryginalne znaczniki czasu oraz sposób synchronizacji;
- lokalizację i orientację kamer, jeżeli są znane;
- zapisane w tym samym czasie snapshoty ADS-B;
- oczekiwane detekcje i ewentualnie niezależnie potwierdzony numer lotu.

Porównujcie LIVE/REPLAY i testy syntetyczne osobno. [Scenariusze testowe](../docs/testing.md).
