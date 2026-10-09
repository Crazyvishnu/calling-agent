"""Explicit model download: python -m scripts.setup_speech --download."""
import argparse
from pathlib import Path
from urllib.request import urlopen
import shutil

ROOT = Path(__file__).resolve().parents[1] / 'backend' / 'models'


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print('Already present:', path.name)
        return
    temporary = path.with_suffix(path.suffix + '.partial')
    try:
        with urlopen(url, timeout=120) as source, temporary.open('wb') as target:
            shutil.copyfileobj(source, target)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    print('Downloaded:', path.name)


def main():
    parser = argparse.ArgumentParser(description='Download English local speech models explicitly; no inference-time downloads.')
    parser.add_argument('--download', action='store_true', help='Download speech model/voice assets (bandwidth and disk required).')
    args = parser.parse_args()
    if not args.download:
        parser.error('Use --download to explicitly request the model downloads.')
    for filename in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'):
        download('https://huggingface.co/Systran/faster-whisper-base.en/resolve/main/' + filename,
                 ROOT / 'whisper-base.en' / filename)
    voice = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high/'
    for filename in ('en_US-ljspeech-high.onnx', 'en_US-ljspeech-high.onnx.json', 'MODEL_CARD'):
        download(voice + filename, ROOT / filename)
    print('Models installed. See docs/LOCAL_SPEECH.md for configuration and licenses.')


if __name__ == '__main__':
    main()
