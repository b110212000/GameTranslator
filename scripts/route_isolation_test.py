"""Verify physical-output audio is excluded from the virtual-cable capture."""
import json
from pathlib import Path
import sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import sounddevice as sd
from audio_devices import read_settings,choose_device,list_input_devices,list_output_devices

settings=read_settings()
capture=choose_device(list_input_devices(),settings.get('capture',{}),True)
output=choose_device(list_output_devices(),settings.get('playback',{}),False)
apis=sd.query_hostapis()
cable=next(i for i,d in enumerate(sd.query_devices()) if 'CABLE Input' in d['name'] and apis[d['hostapi']]['name']=='Windows WASAPI')
blocks=[]
def capture_audio(data,frames,timing,status): blocks.append(data.copy())
def tone(frequency):
    position=0
    def callback(out,frames,timing,status):
        nonlocal position
        signal=np.sin(2*np.pi*frequency*(np.arange(frames)+position)/48000)*0.08
        out[:]=signal[:,None];position+=frames
    return callback
with sd.InputStream(device=capture.index,samplerate=48000,channels=2,dtype='float32',callback=capture_audio), \
     sd.OutputStream(device=output.index,samplerate=48000,channels=2,dtype='float32',callback=tone(1000)):
    time.sleep(1.2)
    boundary=len(blocks)
    with sd.OutputStream(device=cable,samplerate=48000,channels=2,dtype='float32',callback=tone(440)):
        time.sleep(1.2)
isolated=np.concatenate(blocks[:boundary]).mean(axis=1)
routed=np.concatenate(blocks[boundary:]).mean(axis=1)[12000:]
def amplitude(data,frequency):
    return abs(np.mean(data*np.exp(-2j*np.pi*frequency*np.arange(len(data))/48000)))*2
result={'physical_output':output.label,'capture':capture.label,
    'physical_only_rms':float(np.sqrt(np.mean(isolated**2))),
    'cable_440_hz':float(amplitude(routed,440)),'physical_1000_hz_leak':float(amplitude(routed,1000))}
result['passed']=result['physical_only_rms']<0.002 and result['cable_440_hz']>0.03 and result['physical_1000_hz_leak']<0.002
Path('work/route-isolation-040.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
assert result['passed'],result
