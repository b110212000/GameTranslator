"""Offline recorded comparison: forced English versus multilingual Chinese/English."""
import argparse,json,socket,sys,time,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audio_pipeline import RecordedAudioPipeline

def run(fixtures,report):
    def offline(*args,**kwargs): raise RuntimeError('Network disabled for mixed audio test')
    socket.socket.connect=offline
    # An unavailable Windows voice may silently produce an empty WAV. Such a
    # file cannot validate recognition; fail before loading or comparing models.
    for name in ('chinese_only','english_only','mixed'):
        with wave.open(str(fixtures/(name+'.wav'))) as audio:
            if audio.getnframes()/audio.getframerate() < 1:
                raise RuntimeError(f'{name}: invalid/empty speech fixture')
    rows=[]
    for language in ('en','mixed'):
        pipeline=RecordedAudioPipeline(language=language)
        try:
            pipeline.warm_up()
            for name in ('chinese_only','english_only','mixed'):
                start=time.perf_counter()
                captions=pipeline.process_wav(fixtures/(name+'.wav'))
                row={'mode':language,'fixture':name,'seconds':round(time.perf_counter()-start,3),
                     'captions':[caption.to_dict() for caption in captions]}
                rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
        finally: pipeline.close()
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    chinese=next(row for row in rows if row['mode']=='mixed' and row['fixture']=='chinese_only')
    source=' '.join(c['source_text'] for c in chinese['captions'])
    assert any('\u3400'<=char<='\u9fff' for char in source), 'Chinese was not recognized as Chinese'
    assert all(row['captions'] for row in rows if row['mode']=='mixed'), 'Missing mixed-mode captions'

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('fixtures',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();run(args.fixtures,args.report)
