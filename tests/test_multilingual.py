import os
import struct
import unittest
from unittest.mock import patch, Mock
from backend.ai import guard_reply
from backend.speech_engine import LocalSpeechEngine
from backend.vad import EnergyVAD
from scripts.evaluate_speech import score

class MultilingualTests(unittest.TestCase):
    def test_evaluation_counts_wrong_script_as_errors(self):
        self.assertEqual(score('మాట','మాట'),{'wer':0.0,'cer':0.0})
        self.assertEqual(score('मुझे वेबसाइट चाहिए','wrong words')['wer'],1.0)
    def test_endpoint_profile_is_bounded_and_detects_silence(self):
        with patch.dict(os.environ,{'AKKI_ENDPOINT_SILENCE_MS':'400'}):
            vad=EnergyVAD()
        voice=struct.pack('<320h',*([5000,-5000]*160))
        for _ in range(20):vad.feed(voice)
        for _ in range(19):self.assertIsNone(vad.feed(bytes(640))[1])
        self.assertIsNotNone(vad.feed(bytes(640))[1])
        for setting,expected in (('1',15),('999999',50)):
            with patch.dict(os.environ,{'AKKI_ENDPOINT_SILENCE_MS':setting}):self.assertEqual(EnergyVAD().endpoint_frames,expected)
    def test_espeak_text_is_stdin_not_shell_and_never_recorded(self):
        with patch.dict(os.environ,{'TTS_BACKEND_HI':'espeak'}):
            engine=LocalSpeechEngine()
            with patch.object(engine,'status',return_value={'tts_ready':True}),patch.object(engine,'espeak_program',return_value='espeak-ng'),patch('backend.speech_engine.subprocess.run',return_value=Mock(stdout=b'RIFF'+bytes(100))) as synth:
                text='मुझे वेबसाइट चाहिए; $(not-a-command)'
                self.assertTrue(engine.synthesize(text,'hi-IN').startswith(b'RIFF'))
                self.assertEqual(synth.call_args.kwargs['input'],text.encode('utf-8'))
                self.assertNotIn('shell',synth.call_args.kwargs)
                self.assertNotIn(text,synth.call_args.args[0])
    def test_structured_fragments_and_commitments_are_not_spoken(self):
        for reply in ('callback_time": "Friday"}, {','Your website will be developed next week.'):
            self.assertIn('developer must review',guard_reply(reply,'en-IN'))

class WarmupTests(unittest.TestCase):
    def test_warmup_unavailable_and_busy_do_not_start_inference(self):
        import asyncio
        from backend.speech import warm_models, WarmRequest, warm_lock
        from fastapi import HTTPException
        with patch('backend.speech.engine.status',return_value={'ready':False}),patch('backend.telephony.prepare') as prepare:
            with self.assertRaises(HTTPException) as failure:asyncio.run(warm_models(WarmRequest()))
            self.assertEqual(failure.exception.status_code,503);prepare.assert_not_called()
        warm_lock.acquire()
        try:
            with self.assertRaises(HTTPException) as failure:asyncio.run(warm_models(WarmRequest()))
            self.assertEqual(failure.exception.status_code,429)
        finally:warm_lock.release()

class LocalizedSafetyTests(unittest.TestCase):
    def test_localized_opt_out_bypasses_model(self):
        from backend.lab import generate_turn, LabReply
        from backend.language import DECLINE
        for language,message in (('hi-IN','फोन मत करो'),('te-IN','ఫోన్ చేయవద్దు')):
            provider=Mock()
            result=generate_turn({'language':language,'interest':'unknown'},[],{},LabReply(message=message,revision=0),provider)
            provider.reply.assert_not_called()
            self.assertEqual(result['answer'],DECLINE[language]);self.assertEqual(result['state'],'declined')
