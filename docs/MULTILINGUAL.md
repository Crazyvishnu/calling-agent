# Multilingual evaluation and licenses

English, Hindi and Telugu adapters are implemented. Actual Linux synthesis-to-recognition tests ran with local models. These are **synthetic** fixtures, not human speech acceptance.

| Language | Speech generation | Recognition | Current acceptance |
|---|---|---|---|
| English | Piper LJSpeech high | Whisper base.en or multilingual small | Existing synthetic budget/menu smoke passes; human tests pending |
| Hindi | eSpeak NG, GPL software | Multilingual Whisper | Robotic fallback; current synthetic recognition failed accuracy |
| Telugu | Piper padmavathi medium | Multilingual Whisper | Neural synthesis runs; current synthetic recognition failed accuracy |

Both Whisper base and small were tested. Base returned the wrong script for Hindi/Telugu; small still made substantial errors. Installing a model or receiving nonempty text is not sufficient for acceptance. Current non-English speech is experimental and is not enabled for private SIP calling, which remains English-only.

## Setup

```bash
pip install -r backend/requirements-speech.txt
python -m scripts.setup_speech --download --languages en hi te --stt-model small
```

Install eSpeak NG locally (Linux package manager or official Windows installer). Configure private `.env` values:

```dotenv
STT_MODEL_PATH=backend/models/whisper-small
STT_LANGUAGES=en,hi,te
STT_DEVICE=cpu
STT_COMPUTE_TYPE=int8
TTS_BACKEND_HI=espeak
PIPER_VOICE_TE_PATH=backend/models/te_IN-padmavathi-medium.onnx
```

Use `ESPEAK_EXECUTABLE` for a non-PATH executable. `ESPEAK_DATA_PATH`, when needed, points to its `espeak-ng-data` directory. eSpeak text is passed over stdin without a shell. Optional GPU STT requires a compatible CUDA/CTranslate2 installation; on the owner's 4 GB GPU, CPU STT is the recommended starting point.

## Repeatable evaluation

CLI commands inherit environment variables; unlike Uvicorn `--env-file`, they do not automatically load `.env`. In PowerShell set the required `$env:...` variables before running the evaluator.

```bash
python -m scripts.evaluate_speech --output speech-evaluation/synthetic.json
```

The command reports pipeline execution separately from WER/CER accuracy. Word error rate can exceed 1 and is sensitive to punctuation, tokenization and spoken-number normalization. A successful exit by default certifies execution only. Add `--max-wer 0.5` to enforce a chosen accuracy threshold; 0.5 is a diagnostic limit, not a production-quality target. Each result explicitly labels synthetic/human provenance and includes timings. Windows CI publishes only fictional synthetic metrics.

For **consenting human evaluation**, create private mono PCM16 WAV clips, 8–48 kHz and at most 15 seconds each. Keep files and this JSON manifest in ignored `speech-evaluation/`:

```json
[{"file":"english.wav","language":"en-IN","reference":"I need a website with a menu.","consent":true,"provenance":"human"}]
```

Run `python -m scripts.evaluate_speech --manifest speech-evaluation/manifest.json --output speech-evaluation/human-results.json --max-wer 0.2`. References must be accurate human transcriptions. Include accents, Hindi/Telugu code-switching, numbers, business names, opt-outs and silence. Use consenting native speakers to rate voice intelligibility and pronunciation. Test microphone echo, interruption onset, false cutoffs and end-to-end latency separately in the dashboard. Do not upload human recordings or reports to GitHub; remove them according to consent/retention requirements. No human recordings were supplied for this release.

## Selected and rejected voices

- Whisper: MIT software/model ecosystem; [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
- Piper: GPL-3.0 software; distribution obligations still apply. Each voice has separate provenance.
- English LJSpeech high: upstream card identifies public-domain LJSpeech data.
- Telugu padmavathi: [upstream model card](https://huggingface.co/rhasspy/piper-voices/blob/main/te/te_IN/padmavathi/medium/MODEL_CARD) identifies AI4Bharat IndicVoices-R and **CC-BY-4.0** dataset licensing, trained by PravalX. Retain attribution and the model card; validate distribution requirements before shipping weights.
- Hindi pratham/priyamvada cards specify **CC-BY-NC-SA**, so they are not selected for this business application. Rohan and Telugu Maya reference an external IndicTTS license that was not verified; they are not selected.
- English Lessac references a separate research-license agreement and is not substituted merely to improve speed.

Models remain gitignored. The installer preserves a separate model card per voice and never downloads during a live conversation. These license checks do not certify voice quality or commercial telecom authorization.
