"""Isolated synthetic GPU workload; never opens windows or audio devices."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gpu_runtime import cuda_available
from audio_pipeline import load_pcm_wav_as_16khz_mono
from faster_whisper import WhisperModel

parser=argparse.ArgumentParser()
parser.add_argument('wav',type=Path)
parser.add_argument('--begin',type=float,required=True)
parser.add_argument('--duration',type=float,required=True)
args=parser.parse_args()
assert cuda_available(),'GPU unavailable in pressure worker'
audio=load_pcm_wav_as_16khz_mono(args.wav)
model=WhisperModel('base.en',device='cuda',compute_type='int8_float16',local_files_only=True)
calls=0
try:
    while time.monotonic()<args.begin: time.sleep(min(.1,args.begin-time.monotonic()))
    while time.monotonic()<args.begin+args.duration:
        segments,_=model.transcribe(audio,language='en',beam_size=5)
        list(segments);calls+=1
finally:
    model.model.unload_model()
    del model
print(json.dumps({'inferences':calls}),flush=True)
