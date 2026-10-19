"""UI event-loop receiver, including pending sends and texture-only messages."""
import hou,json,time,builtins
from pathlib import Path
from bridge_config import default_exchange,inbox,publish_target,atomic_json

def dispatch_manifest(manifest):
    import texture_reconnect
    manifest=texture_reconnect.local_package(manifest)
    data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    if data.get('kind')=='textures_only':
        result=texture_reconnect.reconnect_manifest(manifest)
        ok=result['updated_image_nodes']>0
        return {'manifest':str(manifest),'ok':ok,'kind':'textures_only','message':'Updated %d existing texture nodes; %d unmatched materials'%(result['updated_image_nodes'],len(result['unmatched_materials'])),'report':result}
    import houdini_importer
    existing=next((n for n in hou.node('/stage').allSubChildren() if n.userData('b2h_manifest')==str(manifest) and n.userData('b2h_verified')=='1'),None)
    stage=houdini_importer.focus_result(existing) if existing else houdini_importer.import_manifest(manifest)
    return {'manifest':str(manifest),'ok':True,'stage':stage.path(),'message':stage.userData('b2h_status') or 'Imported into Solaris'}

def start(exchange=None):
    if not hou.isUIAvailable():return
    import project_assets
    project_assets.install_save_callback()
    previous=getattr(builtins,'_b2h_auto_state',None)
    if previous:
        try:hou.ui.removeEventLoopCallback(previous['callback'])
        except Exception:pass
    state={'seen':set(previous.get('seen',())) if previous else set(),'busy':False,'next_poll':0,'folder':str(default_exchange()),'hip':previous.get('hip') if previous else None}
    def tick():
        if hou.hipFile.isLoadingHipFile() or state['busy'] or time.monotonic()<state['next_poll']:return
        state['next_poll']=time.monotonic()+1;state['busy']=True
        try:
            publish_target();hip=hou.hipFile.path();folder=Path(exchange or default_exchange());state['folder']=str(folder)
            folder.mkdir(parents=True,exist_ok=True)
            if state['hip']!=hip:state['seen'].clear();state['hip']=hip
            for source in dict.fromkeys([folder,inbox()]):
                pointer=source/'latest.json'
                if not pointer.exists():continue
                info=json.loads(pointer.read_text(encoding='utf-8-sig'));manifest=Path(info['manifest'])
                if not manifest.exists():manifest=source/manifest.parent.name/'manifest.json'
                token=(hip,str(manifest),pointer.stat().st_mtime_ns)
                if token in state['seen']:continue
                if manifest.exists():
                    target=json.loads(manifest.read_text(encoding='utf-8-sig')).get('target_hip')
                    if target and Path(target).resolve()!=Path(hip).resolve():continue
                    if source==inbox() and source.resolve()!=folder.resolve() and not target:continue
                state['seen'].add(token)
                try:status=dispatch_manifest(manifest)
                except Exception as error:
                    status={'manifest':str(manifest),'ok':False,'message':str(error)}
                    hou.ui.setStatusMessage('Blender2Houdini: '+str(error),hou.severityType.Error)
                status['source_manifest']=str(manifest)
                atomic_json(source/'houdini_status.json',status);atomic_json(folder/'houdini_status.json',status);state['status']=status
        except Exception as error:state['last_error']=str(error)
        finally:state['busy']=False
    state['callback']=tick;builtins._b2h_auto_state=state
    hou.ui.addEventLoopCallback(tick);publish_target()
    hou.ui.setStatusMessage('Blender2Houdini SAM v011: automatic model / textures-only receiver ready')
    return state
