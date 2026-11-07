"""Replay PCM WAV in real time and measure every original/translation update."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import socket
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from audio_pipeline import load_pcm_wav_as_16khz_mono
from live_captioner import LiveCaptioner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('wav', type=Path)
    parser.add_argument('--language', choices=('en','ja'), default='en')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    def offline(*args, **kwargs): raise RuntimeError('Network disabled in benchmark')
    socket.socket.connect = offline
    audio = load_pcm_wav_as_16khz_mono(args.wav)
    rows, errors = [], []
    started = 0
    def caption(value):
        rows.append({'seconds_after_playback_start':round(time.perf_counter()-started,3), **asdict(value)})
    worker = LiveCaptioner(caption, errors.append, language=args.language)
    try:
        worker.start()
        assert worker.ready.wait(60), errors
        started = time.perf_counter()
        source = np.concatenate((audio,np.zeros(16000,dtype=np.float32)))
        for offset in range(0,len(source),320):
            time.sleep(max(0,started+offset/16000-time.perf_counter()))
            worker.submit(source[offset:offset+320],16000)
        deadline=time.perf_counter()+10
        while time.perf_counter()<deadline:
            finals={(r['segment_id'],r['revision']) for r in rows if r['state']=='recognized'}
            translated={(r['segment_id'],r['revision']) for r in rows if r['state'] in ('translated','error','skipped')}
            if finals and finals <= translated: break
            time.sleep(0.05)
        report={'language':args.language,'backend':worker.backend,'sample_seconds':len(audio)/16000,'captions':rows,'errors':[str(e) for e in errors]}
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'language':args.language,'backend':worker.backend,
            'first_source_seconds':next((r['seconds_after_playback_start'] for r in rows if r['source_text']),None),
            'first_translation_seconds':next((r['seconds_after_playback_start'] for r in rows if r['state']=='translated'),None),
            'finals':[{k:r[k] for k in ('source_text','traditional_chinese_text','recognition_seconds','translation_seconds')} for r in rows if r['state']=='translated' and r['is_final']],
            'errors':report['errors']},ensure_ascii=False,indent=2))
        assert rows and not errors, report
    finally:
        worker.stop()


if __name__ == '__main__': main()
