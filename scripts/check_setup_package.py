"""Silent, isolated install/upgrade/rollback/removal and custom-model checks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import zipfile


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def run(exe,args,expected=0):
    result=subprocess.run([str(exe),*map(str,args)],creationflags=subprocess.CREATE_NO_WINDOW,timeout=240)
    if result.returncode!=expected:raise AssertionError((str(exe),result.returncode,expected))


def fixture(stub,output,malicious=False,corrupt=False):
    archive=output.with_suffix('.zip')
    files={'GameTranslator.exe':b'fixture application','docs/guide.txt':b'fixture guide'}
    if malicious:files['../escape.txt']=b'outside'
    manifest={'Product':'GameTranslator','Version':'0.5.0','Files':[
        {'Name':name,'Size':len(data),'Sha256':'0'*64 if corrupt else hashlib.sha256(data).hexdigest()} for name,data in files.items()]}
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as package:
        package.writestr('package.json',json.dumps(manifest))
        for name,data in files.items():package.writestr(name,data)
    with output.open('wb') as out,stub.open('rb') as prefix,archive.open('rb') as body:
        shutil.copyfileobj(prefix,out);shutil.copyfileobj(body,out)
        out.write(struct.pack('<q',archive.stat().st_size)+b'GTPACK50')


def main():
    p=argparse.ArgumentParser();p.add_argument('--setup',type=Path,required=True);p.add_argument('--stub',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--models',type=Path,required=True);p.add_argument('--wav',type=Path,required=True)
    p.add_argument('--skip-app',action='store_true',help='Reuse prior app checks when only the installer changed')
    args=p.parse_args();args.work.mkdir(parents=True,exist_ok=True)
    result={'version':'0.5.0','passed':False,'mode':'isolated silent install; no registry, shortcuts, windows or audio playback','checks':[]}
    try:
        root=args.work/'Friend 安裝測試';root.mkdir()
        models=args.models.resolve();(models/'keep-model-data.txt').write_text('keep')
        common=['--silent','--no-integrate','--dir',root,'--models',models,'--error-report',args.work/'install-error.txt']
        run(args.setup,common)
        settings=json.loads((root/'settings.json').read_text(encoding='utf-8'))
        assert Path(settings['model_directory'])==models and not settings['setup_completed']
        assert (root/'docs'/'使用教學.html').exists() and (root/'Uninstall.exe').exists()
        manifest=json.loads((root/'install-manifest.json').read_text())
        for file in manifest['Files']:assert digest(root/file['Name'])==file['Sha256']
        result['checks'].append('full install + payload hashes + Unicode/space paths')
        settings.update(capture={'name':'Test cable'},language='ja',subtitle_position={'x':.2,'y':.3})
        (root/'settings.json').write_text(json.dumps(settings,ensure_ascii=False),encoding='utf-8')
        (root/'keep-user-file.txt').write_text('keep')
        run(args.setup,common)
        saved=json.loads((root/'settings.json').read_text(encoding='utf-8'))
        assert saved['capture']==settings['capture'] and saved['language']=='ja' and saved['subtitle_position']==settings['subtitle_position']
        result['checks'].append('upgrade preserves audio/language/subtitle settings')
        if not args.skip_app:
            run(root/'GameTranslator.exe',['--check-setup',args.work/'first-run-exe.json'])
            assert json.loads((args.work/'first-run-exe.json').read_text())['passed']
            run(root/'GameTranslator.exe',['--check-overlay',args.work/'overlay-exe.json'])
            assert json.loads((args.work/'overlay-exe.json').read_text())['passed']
            run(root/'GameTranslator.exe',['--headless','--self-test',args.work/'custom-model-exe.json','--test-wav',args.wav,'--language','en'])
            report=json.loads((args.work/'custom-model-exe.json').read_text(encoding='utf-8'))
            assert report['passed'] and len(report['cycles'])==2
            result['checks'].append('installed EXE: first-run UI + subtitles + two local-model inference cycles')
            result['inference_backends']=[cycle['backend'] for cycle in report['cycles']]
        else:
            result['app_checks']='Unchanged app binary; see prior full-install report'
        run(args.stub,['--silent','--remove',root,'--no-integrate','--error-report',args.work/'remove-error.txt'])
        assert not (root/'GameTranslator.exe').exists() and not (root/'Uninstall.exe').exists()
        assert (root/'settings.json').exists() and (root/'keep-user-file.txt').read_text()=='keep'
        assert (models/'keep-model-data.txt').read_text()=='keep' and (models/'base.en'/'model.bin').exists()
        result['checks'].append('uninstall preserves models, settings and unrelated files')
        small=args.work/'small-setup.exe';fixture(args.stub,small)
        small_root=args.work/'rollback';small_models=small_root/'models'
        small_args=['--silent','--no-integrate','--cpu','--dir',small_root,'--models',small_models]
        run(small,small_args)
        assert json.loads((small_root/'settings.json').read_text())['device']=='cpu'
        before={p.relative_to(small_root):digest(p) for p in small_root.rglob('*') if p.is_file()}
        # Windows holds this existing file open without delete sharing. Commit
        # reaches it after replacing the program, forcing a real rollback.
        with (small_root/'settings.json').open('rb'):
            run(small,[*small_args,'--error-report',args.work/'expected-rollback-error.txt'],expected=1)
        after={p.relative_to(small_root):digest(p) for p in small_root.rglob('*') if p.is_file()}
        assert before==after
        result['checks'].append('locked-file failure rolls back application and settings')
        for label,malicious,corrupt in [('traversal',True,False),('checksum',False,True)]:
            bad=args.work/(label+'.exe');fixture(args.stub,bad,malicious,corrupt)
            run(bad,['--silent','--no-integrate','--dir',args.work/label,'--models',models,'--error-report',args.work/(label+'-expected-error.txt')],expected=1)
            assert not (args.work/'escape.txt').exists()
            assert not (args.work/label/'GameTranslator.exe').exists()
        result['checks'].append('archive traversal and corrupt payload rejected before publishing')
        result['passed']=True
    finally:
        (args.work/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
