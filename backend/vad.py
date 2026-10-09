"""Energy VAD for 20ms PCM16 frames; explicit prototype limits, no cloud dependency."""
from collections import deque
import math
import struct

FRAME_BYTES = 640  # mono 16kHz, signed little-endian 16-bit, 20ms


class EnergyVAD:
    def __init__(self, threshold=0.015):
        self.threshold = threshold
        self.reset()

    def reset(self):
        self.pre_roll = deque(maxlen=10)
        self.buffer = []
        self.voiced = self.silence = 0
        self.active = False

    def feed(self, frame: bytes):
        if len(frame) != FRAME_BYTES:
            raise ValueError('Audio frames must be exactly 640 bytes of 16kHz mono PCM16.')
        samples = struct.unpack('<320h', frame)
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768
        voiced = rms >= self.threshold
        started, utterance = False, None
        if not self.active:
            self.pre_roll.append(frame)
            self.voiced = self.voiced + 1 if voiced else 0
            if self.voiced >= 3:
                self.active, started = True, True
                self.buffer = list(self.pre_roll)
                self.silence = 0
        else:
            self.buffer.append(frame)
            self.silence = 0 if voiced else self.silence + 1
            if self.silence >= 30 or len(self.buffer) >= 750:
                # Trim endpoint silence and refuse very short noise bursts.
                frames = self.buffer[:-self.silence] if self.silence else self.buffer
                if len(frames) >= 12:
                    utterance = b''.join(frames)
                self.reset()
        return started, utterance
