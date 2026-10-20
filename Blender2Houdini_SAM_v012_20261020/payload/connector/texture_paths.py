"""Project-based texture storage. Original basenames are never randomized."""
from pathlib import Path
import hashlib,json,os,re,shutil,uuid

FOLDER='Blender2Houdini_Texture'

def exchange_root(path):
    path=Path(path)
    if path.name==FOLDER:return path
    if path.name.lower()=='exchange':return path.parent/FOLDER
    return path/FOLDER

def project_name(blend_path):
    if not blend_path:raise ValueError('Save the Blender .blend file before sending so its project name can be used')
    name=Path(blend_path).stem
    if not name or re.search(r'[<>:"/\\|?*\x00-\x1f]',name) or name.endswith((' ','.')) or name.upper().split('.')[0] in {'CON','PRN','AUX','NUL',*('COM'+str(i) for i in range(1,10)),*('LPT'+str(i) for i in range(1,10))}:
        raise ValueError('Blender project name is not a valid folder name: '+name)
    return name

def valid_basename(name):
    if not name or name in {'.','..'} or re.search(r'[<>:"/\\|?*\x00-\x1f]',name) or name.endswith((' ','.')) or name.upper().split('.')[0] in {'CON','PRN','AUX','NUL',*('COM'+str(i) for i in range(1,10)),*('LPT'+str(i) for i in range(1,10))}:
        raise ValueError('Texture filename is not a valid filename: '+name)
    return name

def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(data,indent=2),encoding='utf-8');os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()

def write_named(folder,name,source_id,writer):
    """Update the same source; separate different sources with identical names."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);valid_basename(name)
    index_path=folder/'.b2h_texture_index.json'
    index=json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {}
    key=name.casefold();claim=index.get(key);flat=folder/name
    if claim and claim['source_id']==source_id:
        dest=folder/claim['path']
    elif not claim and not flat.exists():
        dest=flat;index[key]={'source_id':source_id,'path':name}
    else:
        dest=folder/'duplicates'/hashlib.sha256(source_id.encode()).hexdigest()[:16]/name
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_name('.'+dest.stem+'.'+uuid.uuid4().hex+dest.suffix)
    try:
        writer(temp)
        if not temp.is_file():raise ValueError('Texture writer did not create '+str(temp))
        os.replace(temp,dest)
        atomic_json(index_path,index)
    finally:
        if temp.exists():temp.unlink()
    return dest

def copy_named(source,folder,source_id=None):
    source=Path(source)
    if not source.is_file():raise FileNotFoundError(source)
    # Already localized files must remain stable on repeated saves.
    folder=Path(folder)
    if source.resolve().is_relative_to(folder.resolve()):return source
    return write_named(folder,source.name,source_id or str(source.resolve()),lambda tmp:shutil.copy2(source,tmp))

def create_transfer(root,blend_path,prefix):
    import datetime
    name=project_name(blend_path);project=exchange_root(root)/name
    packet=project/'.b2h'/(prefix+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    packet.mkdir(parents=True)
    return project,packet,{'project_name':name,'texture_layout':'project-original-names-v1','source_blend':str(blend_path)}
