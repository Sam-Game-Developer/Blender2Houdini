from pathlib import Path
import os,json,time,uuid
from texture_paths import exchange_root,FOLDER
VERSION='v012'
def settings():
    file=Path(os.getenv('APPDATA',str(Path.home()/'.config')))/'BinaryCGI'/'Blender2Houdini'/'settings.json'
    return json.loads(file.read_text(encoding='utf-8-sig')) if file.exists() else {}
def default_exchange():
    import hou
    if not hou.hipFile.isNewFile():return Path(hou.hipFile.path()).resolve().parent/FOLDER
    return inbox()

def inbox():
    return exchange_root(settings().get('exchange') or Path.home()/'Documents'/'BinaryCGI'/'Blender2Houdini'/FOLDER)

def atomic_json(file,data):
    file=Path(file);file.parent.mkdir(parents=True,exist_ok=True)
    temp=file.with_name(file.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(data,indent=2),encoding='utf-8');os.replace(temp,file)

def publish_target():
    import hou
    if not hou.isUIAvailable():return
    file=Path(os.getenv('APPDATA',str(Path.home()/'.config')))/'BinaryCGI'/'Blender2Houdini'/'active_houdini.json'
    atomic_json(file,{'pid':os.getpid(),'updated':time.time(),'hip':hou.hipFile.path(),'exchange':str(default_exchange()),'saved':not hou.hipFile.isNewFile()})


def legacy_exchanges():
    import hou
    paths=[Path(settings().get('exchange') or Path.home()/'Documents'/'BinaryCGI'/'Blender2Houdini'/'exchange')]
    if not hou.hipFile.isNewFile():paths.append(Path(hou.hipFile.path()).resolve().parent/'exchange')
    return list(dict.fromkeys(p for p in paths if p.name!=FOLDER))
