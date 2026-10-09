"""Offline consenting WAV evaluation. Reports synthetic/human provenance explicitly."""
import argparse
import io
import json
from pathlib import Path
import sys
import time
import unicodedata
import wave
from backend.speech_engine import engine

SAMPLES = {
 'en-IN': 'I need a website with a menu. My budget is twelve thousand rupees.',
 'hi-IN': 'मुझे एक वेबसाइट चाहिए। मेरा बजट बारह हजार रुपये है।',
 'te-IN': 'నాకు వెబ్‌సైట్ కావాలి. నా బడ్జెట్ పన్నెండు వేల రూపాయలు.',
}

def pcm16k(wav_bytes):
    import numpy as np
    with wave.open(io.BytesIO(wav_bytes), 'rb') as wav:
        if wav.getnchannels()!=1 or wav.getsampwidth()!=2:
            raise ValueError('Use mono PCM16 WAV audio')
        rate=wav.getframerate(); samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
    if not 8000 <= rate <= 48000 or not 0 < len(samples)/rate <= 15:
        raise ValueError('Audio must contain 0–15 seconds at 8–48kHz')
    positions=np.arange(round(len(samples)*16000/rate))*rate/16000
    return np.interp(positions,np.arange(len(samples)),samples).astype('<i2').tobytes()


def normalized(text):
    value=unicodedata.normalize('NFC',text).casefold()
    return ' '.join(''.join(c if c.isalnum() or unicodedata.category(c).startswith('M') else ' ' for c in value).split())


def distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]


def score(reference,hypothesis):
    r,h=normalized(reference),normalized(hypothesis)
    return {'wer':round(distance(r.split(),h.split())/max(1,len(r.split())),4),
            'cer':round(distance(r,h)/max(1,len(r)),4)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--languages',nargs='+',choices=list(SAMPLES),default=list(SAMPLES))
    parser.add_argument('--manifest',type=Path,help='Private JSON [{file,language,reference,consent:true,provenance:"human"}]')
    parser.add_argument('--output',type=Path,required=True,help='Private output, includes recognized text; never commit human results')
    parser.add_argument('--max-wer',type=float,default=None)
    args=parser.parse_args()
    samples=json.loads(args.manifest.read_text(encoding='utf-8')) if args.manifest else [
        {'language':lang,'reference':SAMPLES[lang],'consent':True,'provenance':'synthetic'} for lang in args.languages]
    if not isinstance(samples,list) or not 1<=len(samples)<=100:parser.error('Use 1–100 samples')
    results=[]
    for sample in samples:
        if sample.get('consent') is not True or sample.get('provenance') not in ('human','synthetic') or sample.get('language') not in SAMPLES:
            parser.error('Every sample needs explicit consent, provenance and a supported language')
        if not isinstance(sample.get('reference'),str) or not 1<=len(sample['reference'])<=2000:parser.error('Invalid reference')
        language=sample['language']; start=time.perf_counter()
        try:
            if args.manifest:
                path=(args.manifest.parent/sample['file']).resolve()
                if path.stat().st_size>2_000_000:raise ValueError('Audio file exceeds the evaluation bound')
                wav=path.read_bytes(); tts_ms=None
            else:
                wav=engine.synthesize(sample['reference'],language);tts_ms=round((time.perf_counter()-start)*1000)
            start=time.perf_counter(); hypothesis=engine.transcribe(pcm16k(wav),language)
            result={'language':language,'provenance':sample['provenance'],'tts_ms':tts_ms,
                    'stt_ms':round((time.perf_counter()-start)*1000),'reference':sample['reference'],'recognized':hypothesis,
                    **score(sample['reference'],hypothesis),'pipeline_passed':bool(hypothesis), 'voice':engine.status(language)['voice_quality']}
            result['accuracy_passed']=result['wer'] <= (args.max_wer if args.max_wer is not None else 0.5)
        except Exception as exc:result={'language':language,'provenance':sample['provenance'],'pipeline_passed':False,'error':type(exc).__name__}
        results.append(result)
        print(language,sample['provenance'],'pipeline OK' if result['pipeline_passed'] else 'pipeline FAIL', 'accuracy PASS' if result.get('accuracy_passed') else 'accuracy FAIL', {k:result.get(k) for k in ('wer','cer','tts_ms','stt_ms')},flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'human_speech_tested':any(r['provenance']=='human' and 'recognized' in r for r in results), 'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    if sys.platform!='win32':args.output.chmod(0o600)
    if not all(r['pipeline_passed'] and (args.max_wer is None or r.get('accuracy_passed',False)) for r in results):raise SystemExit(1)

if __name__=='__main__':main()
