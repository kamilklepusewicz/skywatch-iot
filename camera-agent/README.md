# Camera Agent — osoba 1 (kolega)

Jedna aplikacja Python uruchamiana na dwóch laptopach, z innym `camera_id`.

## Zakres
- Źródła LIVE (kamera USB/wbudowana) i REPLAY (MP4).
- Detekcja samolotów i innych obiektów za pomocą OpenCV / gotowego modelu YOLO.
- Tracking między klatkami, publikacja obserwacji MQTT.
- Publikacja statusów, Last Will, odbiór poleceń `start_live`, `start_replay`, `stop` oraz ACK.
- Oryginalne znaczniki czasu i `scenario_id` dla REPLAY.
- Testy detekcji na nagraniach samolotu oraz pustego nieba.

Planowana struktura (powstaje w trakcie implementacji):
```text
camera-agent/
  src/skywatch_agent/
    main.py
    source.py
    detector.py
    tracker.py
    mqtt_client.py
    replay.py
  tests/
  pyproject.toml
```
**Granica odpowiedzialności:** bez ADS-B, backendu webowego i dashboardu. Zdarzenia zgodne ze [wspólnymi schematami](../shared/contracts/).
