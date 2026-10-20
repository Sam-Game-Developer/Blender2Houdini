"""Keep bridge dependencies beside the HIP when Save As changes its folder."""
from pathlib import Path
import hou,shutil,filecmp,builtins
from bridge_config import default_exchange,atomic_json,publish_target
from texture_paths import FOLDER,copy_named,project_name

def collect(root=None):
    if hou.hipFile.isNewFile():return {'copied':0,'missing':[]}
    exchange=default_exchange();copied=0;missing=[]
    for node in (root or hou.node('/')).allSubChildren():
        parm=node.parm('file') if node.type().name() in ('mtlximage','file') else None
        if not parm or parm.isLocked() or parm.keyframes():continue
        # Scope to bridge materials or geometry, never unrelated scene files.
        ancestor=node;owned=False;manifest=None
        while ancestor and ancestor.path()!='/':
            if ancestor.userData('b2h_manifest'):manifest=ancestor.userData('b2h_manifest')
            if any(ancestor.userData(key) for key in ['b2h_manifest','b2h_source_material','b2h_live_geometry','b2h_simple']):owned=True
            ancestor=ancestor.parent()
        if not owned:continue
        value=parm.eval();filepart,separator,fragment=value.partition('#');source=Path(filepart)
        if not source.is_file():missing.append(node.path());continue
        source=source.resolve()
        if source.is_relative_to(exchange.resolve()):continue
        if FOLDER in source.parts:
            # Save As keeps the source Blender project and relative dependency layout.
            index=len(source.parts)-1-list(reversed(source.parts)).index(FOLDER)
            relative=Path(*source.parts[index+1:])
            dest=exchange/relative
            if node.type().name()=='mtlximage':
                import json
                source_project=Path(*source.parts[:index+2])
                index_file=source_project/'.b2h_texture_index.json'
                names=json.loads(index_file.read_text()) if index_file.is_file() else {}
                claim=names.get(source.name.casefold(),{})
                identity=claim.get('source_id') if claim.get('path')==source.relative_to(source_project).as_posix() else None
                dest=copy_named(source,dest.parent,identity)
            elif dest.exists() and not filecmp.cmp(dest,source,shallow=False):
                dest=copy_named(source,dest.parent)
            else:
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        else:
            project=project_name(Path(hou.hipFile.path()).stem+'.blend')
            if manifest and Path(manifest).is_file():
                import json
                project=json.loads(Path(manifest).read_text(encoding='utf-8-sig')).get('project_name',project)
                project=project_name(project+'.blend')
            target=exchange/project
            if node.type().name()=='file':target=target/'.geometry'
            dest=copy_named(source,target)
        copied+=1
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
