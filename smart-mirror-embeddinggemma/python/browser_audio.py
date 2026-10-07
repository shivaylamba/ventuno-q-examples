"""Audio format for synthesis returned to the browser, without board audio hardware."""
# SPDX-License-Identifier: MPL-2.0

import numpy as np
from arduino.app_peripherals.speaker import BaseSpeaker


class BrowserAudio(BaseSpeaker):
    def __init__(self):
        super().__init__(
            sample_rate=44100, channels=1, format=np.int16,
            buffer_size=4096, auto_reconnect=False,
        )

    def _open_speaker(self):
        # TextToSpeech.synthesize_wav returns PCM to the HTTP client for playback.
        # No ALSA/USB speaker is opened on the board.
        pass

    def _close_speaker(self):
        pass

    def _write_audio(self, audio_chunk):
        raise RuntimeError("Use synthesize_wav and play the returned audio in the browser.")
