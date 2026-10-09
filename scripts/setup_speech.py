"""Explicit local model downloads. No downloads during calls; no paid speech APIs."""
import argparse
from pathlib import Path
from urllib.request import urlopen
import shutil

ROOT = Path(__file__).resolve().parents[1] / 'backend' / 'models'
VOICES = {
    'en': ('en_US-ljspeech-high', 'en/en_US/ljspeech/high', 'Public-domain LJSpeech dataset; retain upstream card'),
    'te': ('te_IN-padmavathi-medium', 'te/te_IN/padmavathi/medium', 'IndicVoices-R dataset CC-BY-4.0; preserve attribution'),
}


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
    print('Downloaded:', path.name, flush=True)


def main():
    parser = argparse.ArgumentParser(description='Explicit offline speech setup; licenses and hardware matter.')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--languages', nargs='+', choices=['en','hi','te'], default=['en'])
    parser.add_argument('--stt-model', choices=['tiny','base','small','base.en'], default=None)
    args = parser.parse_args()
    if not args.download:
        parser.error('Use --download to explicitly request bandwidth/disk-consuming downloads.')
    model = args.stt_model or ('base.en' if args.languages == ['en'] else 'base')
    if model.endswith('.en') and any(lang != 'en' for lang in args.languages):
        parser.error('An English-only STT model cannot recognize Hindi/Telugu.')
    for filename in ('model.bin','config.json','tokenizer.json','vocabulary.txt'):
        download(f'https://huggingface.co/Systran/faster-whisper-{model}/resolve/main/{filename}',
                 ROOT / ('whisper-' + model) / filename)
    for language in dict.fromkeys(args.languages):
        if language == 'hi':
            print('Hindi: install eSpeak NG; set TTS_BACKEND_HI=espeak. This voice is robotic, not a natural voice.')
            continue
        name, folder, license_note = VOICES[language]
        base = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/' + folder + '/'
        for suffix in ('.onnx', '.onnx.json'):
            download(base + name + suffix, ROOT / (name + suffix))
        download(base + 'MODEL_CARD', ROOT / (name + '.MODEL_CARD'))
        print(language + ': ' + license_note)
    print('STT_MODEL_PATH=' + str(ROOT / ('whisper-' + model)))
    print('STT_LANGUAGES=' + ','.join(args.languages))
    if 'te' in args.languages:
        print('PIPER_VOICE_TE_PATH=' + str(ROOT / 'te_IN-padmavathi-medium.onnx'))
    print('No settings changed automatically. See docs/MULTILINGUAL.md.')

if __name__ == '__main__':
    main()
