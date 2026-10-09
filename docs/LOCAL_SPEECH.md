# Local microphone voice prototype

The dashboard now streams microphone PCM to local faster-whisper, sends recognized
text to Ollama, and plays a local Piper WAV reply. It stores text and requirements
drafts in SQLite, not microphone recordings. This is an utterance-based prototype:
STT runs after silence and TTS completes before playback. It does not stream partial
recognition or progressively synthesized speech. An optional [Linux SIP bridge](SIP_AI_BRIDGE.md) connects this pipeline to private Asterisk calls.

## Setup on Windows

First complete [local Ollama setup](LOCAL_AI.md). In the project root, with your
Python virtual environment activated:

```powershell
pip install -r backend/requirements-speech.txt
python -m scripts.setup_speech --download
python -m uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000 --ws-max-size 65536
```

Stop any existing backend before restarting. Run `npm run dev` from `frontend` in
another terminal. The explicit download command fetches English Whisper base.en and
Piper en_US-ljspeech-high assets into gitignored `backend/models`. Downloads need
internet, disk space and bandwidth; inference makes no speech-service API requests.
Do not commit models, credentials, databases or audio. Linux uses the same Python
commands with its virtual environment activated. Windows execution is not yet tested.

In **AI conversation lab**, select a fictional or consenting test lead, confirm the
session collection permission, and start a session. Confirm the separate microphone
processing permission, then choose **Start local microphone**. Use headphones and
say: “I need a restaurant website with a menu. My budget is twelve thousand rupees.”
Review the recognized text and draft; speech recognition and extraction can be wrong.
The opening AI disclosure appears in the session transcript; this prototype starts
listening immediately and does not speak that opening automatically.

**Interrupt reply** stops playback and invalidates pending generation. Detected speech
also interrupts. **Stop microphone**, switching sessions/leads, or closing the panel
releases the microphone and socket. Decline closes the session and persists contact
suppression even if speech generation fails; the closing message is shown as text.

## Timing and interruption limits

- AudioWorklet sends 20 ms mono 16 kHz PCM16 frames. Energy detection needs three
  voiced frames (60 ms), endpoints after 600 ms silence, and caps utterances at 15 s.
- Detection can react to background noise or speaker echo. Browser echo cancellation
  is requested but not established as effective. Use headphones. Human speech,
  accents, noisy rooms and overlapping speakers still need evaluation.
- Ollama token streaming permits cooperative cancellation on its next token. STT/TTS
  CPU kernels cannot be forcibly interrupted; canceled outputs are discarded. Workers
  are serialized per connection so repeated interruptions do not spawn an unbounded
  inference backlog. Cancellation does not erase a turn already committed.
- Separate generation IDs plus SQLite revision checks block stale replies. Consent
  is checked before inference and again before persistence. Raw audio stays in memory.
- A shorter model prompt/schema, disabled Qwen3 thinking, deterministic sampling and
  30-minute model residency reduced the successful CPU text smoke check to about
  6.5 s per turn. This is still too slow for natural phone conversation. See measured
  speech timings and their limits in [verification](VERIFICATION.md).
- Run one Uvicorn worker for this development lab. WebSocket origin restrictions are
  not authentication. Keep all services on localhost. Do not expose this API publicly.

## Languages, licenses and API

English speech alone was exercised. Hindi/Telugu require a multilingual Whisper
model, `STT_MODEL_PATH`, `STT_LANGUAGES=en,hi,te` and matching
`PIPER_VOICE_HI_PATH` / `PIPER_VOICE_TE_PATH` ONNX assets plus companion `.json` files.
Suitable commercially usable voices, pronunciation and accuracy must be assessed
separately; toggling a language does not install or verify a voice. English Piper
uses an American voice, not a validated Indian accent.

Whisper is MIT licensed. Piper software is GPL-3.0; distribution needs review of its
license obligations. The selected LJSpeech voice model card describes public-domain
training data; the piper-voices repository identifies MIT licensing. Preserve and
review upstream model cards and licenses when redistributing or changing voices.

`GET /api/speech/status?language=en-IN` reports dependencies and assets, not quality.
`WS /api/speech/sessions/{id}/ws` requires an active consented session, an allowed
localhost frontend Origin, and initial JSON
`{"type":"start","audio_processing_consent":true}`. Then send 640-byte PCM frames.
JSON controls: `interrupt`, `stop`. Events: `ready`, `interrupt`, `state`, `transcript`,
`result`, `error`. A result includes session snapshot, generation, base64 WAV and
STT/model/TTS milliseconds. The Vite proxy forwards this WebSocket to FastAPI.

Optional English synthesis/recognition check: `python -m scripts.check_local_speech`.
It uses fictional synthesized audio in memory and does not save a recording.

Offline tests: `python -m unittest discover -s tests -v`. These use fake providers
and need no model downloads. Live English speech and private SIP checks are separate.
