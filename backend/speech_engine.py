"""Optional offline STT/TTS adapters. No runtime downloads or audio recordings."""
import importlib.util
import io
import json
import os
from pathlib import Path
from threading import Lock
import wave

from .ai import ProviderUnavailable

# Cache only generic application prompts, never customer-derived replies.
STATIC_PROMPTS = frozenset({
    "Hello, I'm Akki, an AI assistant for a website service. You agreed to this private test and local transcript storage. What website do you need?",
    'Understood. I have ended this conversation and disabled further outreach. Thank you.',
    'I have noted your request for a person. The developer can review your details for a personal follow-up. Thank you.',
})

MODEL_ROOT = Path(__file__).parent / 'models'


class LocalSpeechEngine:
    def __init__(self):
        self.stt_path = Path(os.environ.get('STT_MODEL_PATH', str(MODEL_ROOT / 'whisper-base.en')))
        self.stt_languages = os.environ.get('STT_LANGUAGES', 'en').split(',')
        self._recognizer = None
        self._voices = {}
        self._static_audio = {}
        self._stt_lock, self._tts_lock = Lock(), Lock()

    def voice_path(self, language):
        prefix = language.split('-')[0]
        setting = os.environ.get('PIPER_VOICE_' + prefix.upper() + '_PATH')
        return Path(setting) if setting else (MODEL_ROOT / 'en_US-ljspeech-high.onnx' if prefix == 'en' else None)

    def status(self, language='en-IN'):
        prefix = language.split('-')[0]
        path = self.voice_path(language)
        stt = importlib.util.find_spec('faster_whisper') is not None and (self.stt_path / 'model.bin').is_file() and prefix in self.stt_languages
        tts = importlib.util.find_spec('piper') is not None and path is not None and path.is_file() and Path(str(path) + '.json').is_file()
        if tts:
            try:
                config = json.loads(Path(str(path) + '.json').read_text())
                tts = config['language']['code'].split('_')[0] == prefix
            except (OSError, ValueError, KeyError, TypeError):
                tts = False
        return {'stt_ready': stt, 'tts_ready': tts, 'ready': stt and tts,
                'language': language, 'audio_recordings_stored': False,
                'detail': 'Local speech assets available' if stt and tts else 'Install optional speech dependencies/models; this language needs matching local STT and Piper assets.'}

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
                    self._recognizer = WhisperModel(str(self.stt_path), device='cpu', compute_type='int8',
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
            raise ProviderUnavailable('Local Piper speech generation is unavailable for this language.')
        if not text.strip() or len(text) > 2000:
            raise ValueError('Speech text must contain 1–2000 characters.')
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
                        config=PiperConfig.from_dict(json.loads(Path(str(path) + '.json').read_text())),
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
