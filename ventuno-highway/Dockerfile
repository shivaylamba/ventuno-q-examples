# Arduino image includes matching QAIRT/TFLite and licensed quantized hand models.
FROM ghcr.io/arduino/app-bricks/gesture-recognition-runner@sha256:d9098e25723fcf5a12eb748dedcf0a139ec74719d595cf2637ab331ccf7c393c
RUN python -m pip install --no-cache-dir PyYAML==6.0.2
COPY perception /engine/perception
COPY gestures /engine/gestures
COPY telemetry /engine/telemetry
COPY config /engine/config
ENV PYTHONPATH=/engine:/app:/opt
ENTRYPOINT ["python", "/engine/perception/worker.py"]
