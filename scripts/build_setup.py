"""Build the native wizard plus a streamed ZIP payload, with file hashes."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
import shutil
import struct
import subprocess
import sys
import zipfile


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def collect_notices(destination):
    """Preserve installed distribution license texts alongside the runtime licenses."""
    destination.mkdir(parents=True,exist_ok=True)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.is_file():shutil.copy2(python_license,destination/'Python-LICENSE.txt')
    rows=[]
    # Collect licenses from the build environment as a conservative superset.
    # A listed distribution is not a promise that all its modules are bundled.
    for dist in metadata.distributions():
        name=dist.metadata.get('Name','unknown')
        safe=''.join(c if c.isalnum() or c in '-_.' else '_' for c in name)
        files=[]
        for file in dist.files or []:
            if '.dist-info' not in str(file) and '.egg-info' not in str(file): continue
            if not any(token in file.name.lower() for token in ('license','copying','notice')): continue
            source=Path(dist.locate_file(file))
            if not source.is_file(): continue
            target=destination/safe/Path(*file.parts[1:])
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target);files.append(str(target.relative_to(destination)))
        rows.append({'name':name,'version':dist.version,'license_files':files})
    (destination/'inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'README.txt').write_text('Third-party notices collected from the build environment. This is a conservative superset; not every module of every listed distribution is bundled. NVIDIA runtime notices are in runtime/licenses. Model licenses accompany their respective downloads.\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--release',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    args.work.mkdir(parents=True,exist_ok=True);args.output.parent.mkdir(parents=True,exist_ok=True)
    stub=args.work/'SetupStub.exe'
    compiler=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET'/'Framework64'/'v4.0.30319'/'csc.exe'
    subprocess.run([str(compiler),'/nologo','/codepage:65001','/target:winexe','/platform:x64','/optimize+',f'/out:{stub}',
        f'/win32manifest:{root / "setup.manifest"}',
        '/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.IO.Compression.dll',
        '/r:System.IO.Compression.FileSystem.dll','/r:System.Web.Extensions.dll','/r:Microsoft.CSharp.dll',str(root/'Setup.cs')],check=True)
    shutil.copy2(stub,args.release/'Uninstall.exe')
    collect_notices(args.release/'licenses')
    files=[args.release/'GameTranslator.exe',args.release/'Uninstall.exe']
    for folder in ('runtime','docs','licenses'):
        files.extend(p for p in (args.release/folder).rglob('*') if p.is_file())
    manifest={'Product':'GameTranslator','Version':'0.5.0','Files':[
        {'Name':p.relative_to(args.release).as_posix(),'Size':p.stat().st_size,'Sha256':sha256(p)} for p in sorted(files)]}
    archive=args.work/'payload.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as package:
        package.writestr('package.json',json.dumps(manifest,ensure_ascii=False))
        for file in sorted(files):package.write(file,file.relative_to(args.release).as_posix())
    with args.output.open('wb') as output,stub.open('rb') as prefix,archive.open('rb') as payload:
        shutil.copyfileobj(prefix,output);shutil.copyfileobj(payload,output)
        output.write(struct.pack('<q',archive.stat().st_size)+b'GTPACK50')
    receipt={'version':'0.5.0','bytes':args.output.stat().st_size,'sha256':sha256(args.output),'payload_files':len(files),'unpacked_bytes':sum(f['Size'] for f in manifest['Files'])}
    args.output.with_suffix('.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt))


if __name__=='__main__':main()
