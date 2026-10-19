from pathlib import Path
import json,zipfile,hashlib,ast
ROOT=Path(__file__).resolve().parent;prefix=ROOT.name
results={'release':prefix,'version':[0,0,8],'date':'20261019'}
for name in ['blender_report','houdini_report','return_report','resend_report']:
    results[name]=json.loads((ROOT/'tests'/(name+'.json')).read_text())
(ROOT/'TEST_RESULTS.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
files=[ROOT/name for name in ['Install.cmd','Install_Houdini.cmd','Install.ps1','INSTALL_v008.txt','TEST_RESULTS.json']]+[p for p in (ROOT/'payload').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'))
outputs=[]
for kind in ['Installer','HoudiniConnector']:
    path=ROOT/(prefix+'_'+kind+'.zip')
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,prefix+'/'+p.relative_to(ROOT).as_posix())
        if kind=='Installer':z.write(ROOT/(prefix+'_BlenderAddon.zip'),prefix+'/'+prefix+'_BlenderAddon.zip')
    outputs.append(path)
outputs.append(ROOT/(prefix+'_BlenderAddon.zip'))
reports=[]
for path in outputs:
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
    reports.append({'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'crc':'PASS'})
(ROOT/'RELEASE_CHECKSUMS.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports,indent=2))
