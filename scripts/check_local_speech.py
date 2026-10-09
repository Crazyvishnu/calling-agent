"""English local TTS→STT smoke check with fictional text and no saved audio."""
import io
import time
import wave

from backend.speech_engine import engine


def main():
    if not engine.status()['ready']:
        raise SystemExit('Install backend/requirements-speech.txt and run python -m scripts.setup_speech --download first.')
    import numpy as np
    started = time.perf_counter()
    wav = engine.synthesize('I need a restaurant website with a menu. My budget is twelve thousand rupees.', 'en-IN')
    tts_seconds = time.perf_counter() - started
    with wave.open(io.BytesIO(wav), 'rb') as audio:
        assert audio.getnchannels() == 1 and audio.getsampwidth() == 2
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2')
        rate = audio.getframerate()
    # Smoke-fixture resampling only; browser capture uses its own AudioWorklet.
    positions = np.arange(round(len(samples) * 16000 / rate)) * rate / 16000
    pcm = np.interp(positions, np.arange(len(samples)), samples).astype('<i2').tobytes()
    started = time.perf_counter()
    text = engine.transcribe(pcm, 'en-IN')
    stt_seconds = time.perf_counter() - started
    assert 'menu' in text.lower(), 'Menu not recognized: ' + text
    assert '12000' in text.replace(',', '') or 'twelve thousand' in text.lower(), 'Budget not recognized: ' + text
    print('Local English speech smoke passed:', text)
    print(f'TTS {tts_seconds:.2f}s; STT {stt_seconds:.2f}s (includes model initialization). No audio saved.')


if __name__ == '__main__':
    main()
