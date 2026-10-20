from pathlib import Path
import ast,json,hashlib,zipfile
root=Path(__file__).resolve().parent;prefix=root.name
for p in (root/'payload').rglob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
files=[root/name for name in ['Install.cmd','Install_Houdini.cmd','Install.ps1','INSTALL_v012.txt','TEST_RESULTS.json']]+[p for p in (root/'payload').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
checks=[]
for kind in ['Installer','HoudiniConnector']:
    path=root/(prefix+'_'+kind+'.zip')
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,prefix+'/'+p.relative_to(root).as_posix())
        if kind=='Installer':z.write(root/(prefix+'_BlenderAddon.zip'),prefix+'/'+prefix+'_BlenderAddon.zip')
for path in sorted(root.glob(prefix+'_*.zip')):
    with zipfile.ZipFile(path) as z:assert z.testzip() is None
    checks.append({'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(root/'RELEASE_CHECKSUMS.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
