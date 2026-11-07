"""Fetch one CC BY 4.0 Google FLEURS clip, without downloading its full archive."""
import io
import json
from pathlib import Path
import tarfile
import urllib.request
import wave
import av
import numpy as np


def main():
    root = Path(__file__).resolve().parents[1]
    base = 'https://huggingface.co/datasets/google/fleurs/resolve/main/data/ja_jp/'
    with urllib.request.urlopen(base + 'test.tsv', timeout=30) as response:
        rows = [line.split('\t') for line in response.read().decode('utf-8').splitlines()]
    with urllib.request.urlopen(base + 'audio/test.tar.gz', timeout=30) as response:
        with tarfile.open(fileobj=response, mode='r|gz') as archive:
            for member in archive:
                if member.isfile() and member.name.endswith('.wav'):
                    # Read only this member, never extract archive paths to disk.
                    raw = archive.extractfile(member).read()
                    filename = Path(member.name).name
                    break
            else:
                raise RuntimeError('The archive contains no WAV recording')
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    samples = []
    with av.open(io.BytesIO(raw)) as container:
        for frame in container.decode(audio=0):
            samples.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(frame))
    samples.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(None))
    audio = np.concatenate(samples)
    (root/'samples').mkdir(exist_ok=True)
    with wave.open(str(root/'samples/japanese_fleurs.wav'), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(audio.astype('<i2').tobytes())
    info = {'source': base+'audio/test.tar.gz', 'file': filename, 'seconds': len(audio)/16000,
            'transcript': next(r[2] for r in rows if r[1] == filename),
            'license': 'CC BY 4.0, Google FLEURS'}
    (root/'work').mkdir(exist_ok=True)
    (root/'work/japanese-fixture.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved samples/japanese_fleurs.wav and work/japanese-fixture.json')


if __name__ == '__main__': main()
