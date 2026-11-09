"""Real cable soak: clean/noisy/overlapping audio, slow translation, queue/memory bounds."""
import argparse
from collections import deque
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import sounddevice as sd
from audio_devices import read_settings,choose_device,list_input_devices,list_output_devices
from audio_pipeline import RecordedAudioPipeline,load_pcm_wav_as_16khz_mono
from audio_router import AudioRoute,AudioRouter
from live_captioner import LiveCaptioner


def memory_mb():
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in (
            'peak','working','quota_peak_paged','quota_paged','quota_peak_nonpaged','quota_nonpaged','pagefile','peak_pagefile')]
    value=Counters();value.cb=ctypes.sizeof(value)
    api=ctypes.WinDLL('psapi')
    api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    if not api.GetProcessMemoryInfo(ctypes.c_void_p(-1),ctypes.byref(value),value.cb): return 0
    return value.working/1048576


def run(wav,language,seconds,report,gpu_contention=False,silent=False,contention_start=150,contention_duration=60):
    def offline(*args,**kwargs): raise RuntimeError('Network is disabled in soak test')
    socket.socket.connect=offline
    started=0.0
    errors=[]
    source_count=translated_count=0
    latency=deque(maxlen=2000)
    samples=[]
    pressure_process=None
    pressure_calls=0
    class StressPipeline(RecordedAudioPipeline):
        def translate(self,text):
            # Deliberately slow only translation during a bounded test phase.
            elapsed=time.monotonic()-started if started else 0
            if 30 <= elapsed < 75: time.sleep(1.5)
            return super().translate(text)
    def receive(update):
        nonlocal source_count,translated_count
        if update.source_text and update.state in ('partial','recognized'): source_count+=1
        if update.state=='translated':
            translated_count+=1;latency.append(update.after_speech_seconds)
    engine=LiveCaptioner(receive,errors.append,language=language,
                         pipeline_factory=lambda:StressPipeline(language=language))
    settings=read_settings()
    capture=choose_device(list_input_devices(),settings.get('capture',{}),True)
    output=choose_device(list_output_devices(),settings.get('playback',{}),False)
    assert capture and output and 'CABLE Output' in capture.name
    apis=sd.query_hostapis()
    cable=next(i for i,d in enumerate(sd.query_devices()) if 'CABLE Input' in d['name'] and apis[d['hostapi']]['name']=='Windows WASAPI')
    clean=np.repeat(load_pcm_wav_as_16khz_mono(wav),3)
    clean=np.concatenate([clean,np.zeros(48000,dtype=np.float32)])
    noise=np.random.default_rng(42).normal(0,0.008,len(clean)).astype(np.float32)
    mixed=np.clip(clean+np.roll(clean,32000)*0.35+noise,-1,1)
    cursor=0
    def play(outdata,frames,_time,_status):
        nonlocal cursor
        elapsed=time.monotonic()-started
        source=mixed if 90 <= elapsed < 150 else clean
        indexes=(np.arange(frames)+cursor)%len(source)
        outdata[:]=source[indexes,None]
        cursor=(cursor+frames)%len(source)
    router=None if silent else AudioRouter(AudioRoute(capture.index,output.index),engine.submit)
    player=None
    result={'passed':False,'language':language,'duration_seconds':seconds,'samples':samples,
            'audio_mode':'silent PCM replay' if silent else 'real cable and headphones',
            'contention_window':[contention_start,contention_start+contention_duration] if gpu_contention else None}
    try:
        engine.start();assert engine.ready.wait(90),errors
        if router:
            router.start()
            player=sd.OutputStream(device=cable,samplerate=48000,channels=2,dtype='float32',blocksize=960,callback=play)
        started=time.monotonic()
        if gpu_contention and engine.backend=='GPU':
            pressure_process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('gpu_contention_worker.py')),
                str(wav.resolve()),'--begin',str(started+contention_start),'--duration',str(contention_duration)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        if player: player.start()
        next_feed=0.0
        next_report=0
        while time.monotonic()-started < seconds:
            elapsed=time.monotonic()-started
            assert not errors,errors
            if router:
                assert router.is_running,'Audio streams stopped'
                assert time.perf_counter()-router.last_capture_at < 3 if router.last_capture_at else elapsed < 3
            elif elapsed>=next_feed:
                block=np.empty((960,2),dtype=np.float32)
                play(block,960,None,None);engine.submit(block,48000)
                next_feed+=0.02
            if elapsed>=next_report:
                stats=engine.snapshot()
                item={'seconds':round(elapsed,1),'rss_mb':round(memory_mb(),1),
                      'captured_frames':router.captured_frames if router else None,
                      'played_frames':router.played_frames if router else None,**stats}
                samples.append(item)
                print(json.dumps(item),flush=True)
                assert stats['audio_queue']<=200 and stats['recognition_queue']<=3 and stats['translation_queue']<=6
                next_report+=15
            time.sleep(min(0.02,max(0,started+next_feed-time.monotonic())) if silent else 0.1)
        if pressure_process:
            pressure_output,pressure_error=pressure_process.communicate(timeout=30)
            assert pressure_process.returncode==0,(pressure_process.returncode,pressure_error)
            pressure_calls=json.loads(pressure_output)['inferences']
        result.update(source_updates=source_count,translations=translated_count,
            capture_device=capture.label,output_device=output.label,backend=engine.backend,
            translation_route=engine.translation_route,final_stats=engine.snapshot(),
            passthrough_ratio=router.played_frames/max(1,router.captured_frames) if router else None,
            playback_dropped_blocks=router.playback_drops if router else None,
            input_overflows=router.input_overflows if router else None,
            output_underflows=router.output_underflows if router else None,
            gpu_contention_inferences=pressure_calls,
            p95_after_speech_seconds=float(np.percentile(latency,95)) if latency else None)
        assert source_count>=3 and translated_count>=3,result
        if router:
            assert result['passthrough_ratio']>0.98,result
            assert result['playback_dropped_blocks']*960/max(1,router.captured_frames)<0.01,result
        if gpu_contention and pressure_process:
            assert pressure_calls > 0, 'GPU contention phase did not run'
        if len(samples)>10:
            growth=samples[-1]['rss_mb']-samples[len(samples)//2]['rss_mb']
            result['late_memory_growth_mb']=round(growth,1)
            assert growth<256,result
        result['passed']=True
    except Exception as error:
        result['error']=str(error)
        raise
    finally:
        if player: player.abort();player.close()
        if router: router.stop()
        engine.stop()
        if pressure_process and pressure_process.poll() is None:
            pressure_process.terminate();pressure_process.communicate(timeout=15)
        for thread in [engine._thread,*engine._workers]:
            if thread: thread.join(timeout=10)
        result['workers_stopped']=not engine.is_alive
        if not result['workers_stopped']:
            result['passed']=False
            result['error']='Workers did not stop'
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert result['passed'],result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('wav',type=Path)
    parser.add_argument('--language',choices=('en','ja','mixed'),default='en')
    parser.add_argument('--minutes',type=float,default=5)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--gpu-contention',action='store_true')
    parser.add_argument('--silent',action='store_true',help='Replay PCM without opening audio endpoints')
    parser.add_argument('--contention-start',type=float,default=150)
    parser.add_argument('--contention-duration',type=float,default=60)
    args=parser.parse_args()
    run(args.wav,args.language,args.minutes*60,args.report,args.gpu_contention,args.silent,
        args.contention_start,args.contention_duration)
