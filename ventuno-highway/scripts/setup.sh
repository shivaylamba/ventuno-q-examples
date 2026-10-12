#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker image inspect local/ai-reality-perception:1.0.0 >/dev/null 2>&1 || docker build -t local/ai-reality-perception:1.0.0 .
mkdir -p runtime/arduino-dsp runs
python3 - <<'PY'
from pathlib import Path
import re
p=Path('bricks/highway_perception/brick_compose.yaml')
text=re.sub(r'^      - /dev/video\d+:/dev/video\d+\n', '', p.read_text(), flags=re.M)
devices=''.join(f'      - {device}:{device}\n' for device in sorted(Path('/dev').glob('video[0-9]*')))
if not devices:
    raise SystemExit('Connect the USB webcam before setup; no /dev/video devices are available.')
p.write_text(text.replace('    devices:\n', '    devices:\n'+devices))
PY
if [ -d /home/arduino/ai-reality-engine/runtime/arduino-dsp ]; then
    cp /home/arduino/ai-reality-engine/runtime/arduino-dsp/* runtime/arduino-dsp/
else
    cp /usr/share/qcom/qcs8300/Qualcomm/QCS8300-RIDE/dsp/cdsp/* runtime/arduino-dsp/
    helper=$(docker create local/ai-reality-perception:1.0.0)
    trap 'docker rm "$helper" >/dev/null' EXIT
    docker cp "$helper":/usr/share/qcom/qcs8300/Qualcomm/QCS8300-RIDE/dsp/cdsp/. runtime/arduino-dsp/
fi
echo 'Prepared board hand runtime. Launch this app from App Lab.'
