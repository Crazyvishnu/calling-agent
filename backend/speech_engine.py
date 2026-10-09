"""Optional offline STT/TTS adapters. No runtime downloads or audio recordings."""
import importlib.util
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from threading import Lock
import wave

from .ai import ProviderUnavailable
from .language import DECLINE, HANDOFF

# Cache only generic application prompts, never customer-derived replies.
STATIC_PROMPTS = frozenset({*DECLINE.values(), *HANDOFF.values(),
    "Hello, I'm Akki, an AI assistant for a website service. You agreed to this private test and local transcript storage. What website do you need?",
    'Understood. I have ended this conversation and disabled further outreach. Thank you.',
    'I have noted your request for a person. The developer can review your details for a personal follow-up. Thank you.',
})

MODEL_ROOT = Path(__file__).parent / 'models'


class LocalSpeechEngine:
    def __init__(self):
        self.stt_path = Path(os.environ.get('STT_MODEL_PATH', str(MODEL_ROOT / 'whisper-base.en')))
        self.stt_languages = [x.strip() for x in os.environ.get('STT_LANGUAGES', 'en').split(',')]
        self.stt_device = os.environ.get('STT_DEVICE', 'cpu')
        self.stt_compute_type = os.environ.get('STT_COMPUTE_TYPE', 'int8')
        self._recognizer = None
        self._voices = {}
        self._static_audio = {}
        self._stt_lock, self._tts_lock = Lock(), Lock()

    def voice_path(self, language):
        prefix = language.split('-')[0]
        setting = os.environ.get('PIPER_VOICE_' + prefix.upper() + '_PATH')
        return Path(setting) if setting else (MODEL_ROOT / 'en_US-ljspeech-high.onnx' if prefix == 'en' else None)

    def tts_backend(self, language):
        return os.environ.get('TTS_BACKEND_' + language.split('-')[0].upper(), 'piper')

    def espeak_program(self):
        return shutil.which(os.environ.get('ESPEAK_EXECUTABLE', 'espeak-ng'))

    def status(self, language='en-IN'):
        prefix = language.split('-')[0]
        path = self.voice_path(language)
        stt = importlib.util.find_spec('faster_whisper') is not None and (self.stt_path / 'model.bin').is_file() and prefix in self.stt_languages
        tts = importlib.util.find_spec('piper') is not None and path is not None and path.is_file() and Path(str(path) + '.json').is_file()
        if tts:
            try:
                config = json.loads(Path(str(path) + '.json').read_text(encoding='utf-8'))
                tts = config['language']['code'].split('_')[0] == prefix
            except (OSError, ValueError, KeyError, TypeError):
                tts = False
        backend = self.tts_backend(language)
        if backend == 'espeak':
            tts = prefix in ('en','hi','te') and self.espeak_program() is not None
        elif backend != 'piper':
            tts = False
        return {'tts_backend': backend, 'voice_quality': 'robotic fallback' if backend == 'espeak' else 'neural voice; human quality unverified',
                'stt_device': self.stt_device, 'human_validated': False,
                'language_acceptance': 'human validation pending' if prefix=='en' else 'experimental; recognition acceptance failed on current synthetic samples',
                'endpoint_silence_ms': max(300,min(1000,int(os.environ.get('AKKI_ENDPOINT_SILENCE_MS','600'))//20*20)),
                'stt_ready': stt, 'tts_ready': tts, 'ready': stt and tts,
                'language': language, 'audio_recordings_stored': False,
                'detail': 'Local speech assets available' if stt and tts else 'Install matching local STT and configured TTS assets; readiness is not an accuracy or quality certificate.'}

    def transcribe(self, pcm: bytes, language: str) -> str:
        if not self.status(language)['stt_ready']:
            raise ProviderUnavailable('Local speech recognition is unavailable for this language.')
        if not pcm or len(pcm) % 2 or len(pcm) > 16000 * 2 * 15:
            raise ValueError('Expected at most 15 seconds of mono 16kHz PCM16 audio.')
        try:
            import numpy as np
            from faster_whisper import WhisperModel
            with self._stt_lock:
                if self._recognizer is None:
                    self._recognizer = WhisperModel(str(self.stt_path), device=self.stt_device, compute_type=self.stt_compute_type,
                                                    cpu_threads=2, num_workers=1, local_files_only=True)
                if language.split('-')[0] != 'en' and not self._recognizer.model.is_multilingual:
                    raise ProviderUnavailable('This STT model is English-only; install a multilingual model for this language.')
                segments, _ = self._recognizer.transcribe(
                    np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768,
                    language=language.split('-')[0], beam_size=1, best_of=1,
                    condition_on_previous_text=False, vad_filter=False,
                )
                text = ' '.join(s.text.strip() for s in segments).strip()
            return text[:2000]
        except (ImportError, RuntimeError, OSError, ValueError) as exc:
            raise ProviderUnavailable('Local STT failed; check the model files and optional dependencies.') from exc

    def synthesize(self, text: str, language: str) -> bytes:
        if not self.status(language)['tts_ready']:
            raise ProviderUnavailable('Local speech generation is unavailable for this language.')
        if not text.strip() or len(text) > 2000:
            raise ValueError('Speech text must contain 1–2000 characters.')
        if self.tts_backend(language) == 'espeak':
            try:
                args = [self.espeak_program(), '--stdout', '--stdin', '-v', language.split('-')[0], '-s', '155']
                # Text is stdin data, never a shell command. No files or audio devices used.
                result = subprocess.run(args, input=text.encode('utf-8'), stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, timeout=30, check=True)
                if not result.stdout.startswith(b'RIFF') or len(result.stdout) > 8_000_000:
                    raise ValueError('Invalid or oversized synthesized audio')
                return result.stdout
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                raise ProviderUnavailable('Local eSpeak NG synthesis failed; check the executable and voice data.') from exc
        try:
            from piper import PiperVoice
            from piper.config import PiperConfig
            import onnxruntime
            with self._tts_lock:
                cache_key = (language, text)
                if text in STATIC_PROMPTS and cache_key in self._static_audio:
                    return self._static_audio[cache_key]
                if language not in self._voices:
                    path = self.voice_path(language)
                    options = onnxruntime.SessionOptions()
                    options.intra_op_num_threads = 2
                    options.inter_op_num_threads = 1
                    self._voices[language] = PiperVoice(
                        config=PiperConfig.from_dict(json.loads(Path(str(path) + '.json').read_text(encoding='utf-8'))),
                        session=onnxruntime.InferenceSession(str(path), sess_options=options,
                                                            providers=['CPUExecutionProvider']),
                    )
                output = io.BytesIO()
                with wave.open(output, 'wb') as wav:
                    self._voices[language].synthesize_wav(text, wav)
                result = output.getvalue()
                if text in STATIC_PROMPTS:
                    self._static_audio[cache_key] = result
            return result
        except (ImportError, RuntimeError, OSError, ValueError) as exc:
            raise ProviderUnavailable('Local Piper synthesis failed; check the voice files and optional dependencies.') from exc


engine = LocalSpeechEngine()
