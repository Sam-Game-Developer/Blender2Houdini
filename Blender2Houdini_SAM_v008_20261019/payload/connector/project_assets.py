"""Keep bridge dependencies beside the HIP when Save As changes its folder."""
from pathlib import Path
import hou,shutil,hashlib,builtins
from bridge_config import default_exchange,atomic_json,publish_target

def collect(root=None):
    if hou.hipFile.isNewFile():return {'copied':0,'missing':[]}
    exchange=default_exchange();target=exchange/'collected';copied=0;missing=[]
    for node in (root or hou.node('/')).allSubChildren():
        parm=node.parm('file') if node.type().name() in ('mtlximage','file') else None
        if not parm or parm.isLocked() or parm.keyframes():continue
        # Scope to bridge materials or geometry, never unrelated scene files.
        ancestor=node;owned=False
        while ancestor and ancestor.path()!='/':
            if any(ancestor.userData(key) for key in ['b2h_manifest','b2h_source_material','b2h_live_geometry','b2h_simple']):owned=True;break
            ancestor=ancestor.parent()
        if not owned:continue
        value=parm.eval();filepart,separator,fragment=value.partition('#');source=Path(filepart)
        if not source.is_file():missing.append(node.path());continue
        source=source.resolve()
        if source.is_relative_to(exchange.resolve()):continue
        # Path-derived name avoids hashing multi-gigabyte FBX files on every save.
        dest=target/(hashlib.sha256(str(source).encode()).hexdigest()[:12]+'_'+source.name)
        target.mkdir(parents=True,exist_ok=True)
        if not dest.exists() or dest.stat().st_size!=source.stat().st_size or dest.stat().st_mtime_ns!=source.stat().st_mtime_ns:shutil.copy2(source,dest);copied+=1
        parm.set(dest.as_posix()+(separator+fragment if separator else ''))
    report={'copied':copied,'missing':missing,'exchange':str(exchange)};atomic_json(exchange/'asset_collection_report.json',report);return report

def install_save_callback():
    previous=getattr(builtins,'_b2h_save_callback',None)
    if previous:
        try:hou.hipFile.removeEventCallback(previous)
        except Exception:pass
    state={'busy':False}
    def callback(event):
        if state['busy'] or event!=hou.hipFileEventType.BeforeSave:return
        state['busy']=True
        try:collect();publish_target()
        except Exception as error:
            if hou.isUIAvailable():hou.ui.setStatusMessage('Blender2Houdini asset collection: '+str(error),hou.severityType.Warning)
        finally:state['busy']=False
    hou.hipFile.addEventCallback(callback);builtins._b2h_save_callback=callback
