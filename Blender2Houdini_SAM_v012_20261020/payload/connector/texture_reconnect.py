"""Relink existing image nodes, without changing geometry or shader graphs."""
from pathlib import Path
import json,hashlib,shutil,hou,uuid
from bridge_config import default_exchange,atomic_json
from texture_paths import copy_named,project_name

def local_package(manifest):
    manifest=Path(manifest).resolve()
    data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    if data.get('texture_layout')=='project-original-names-v1':
        project=project_name(data['project_name']+'.blend')
        source_project=manifest.parents[2]
        if manifest.parent.parent.name!='.b2h' or source_project.name!=project:
            raise ValueError('Invalid project texture package layout')
        dest_project=default_exchange()/project
        if source_project.resolve()==dest_project.resolve():return manifest
        packet=dest_project/'.b2h'/manifest.parent.name
        if packet.exists():
            local=packet/'manifest.json'
            if local.is_file() and json.loads(local.read_text()).get('source_manifest')==str(manifest):return local
            packet=packet.with_name(packet.name+'_'+uuid.uuid4().hex[:6])
        packet.parent.mkdir(parents=True,exist_ok=True)
        staging=packet.with_name(packet.name+'.partial_'+uuid.uuid4().hex[:6])
        try:
            shutil.copytree(manifest.parent,staging)
            for material in data.get('materials',{}).values():
                for texture in material.get('maps',{}).values():
                    source=(manifest.parent/texture['path']).resolve()
                    if not source.is_relative_to(source_project.resolve()):raise ValueError('Texture outside project: '+str(source))
                    dest=copy_named(source,dest_project,texture.get('source_id') or str(source))
                    texture['path']='../../'+dest.relative_to(dest_project).as_posix()
            data['source_manifest']=str(manifest)
            atomic_json(staging/'manifest.json',data);staging.rename(packet)
        finally:
            if staging.exists():shutil.rmtree(staging)
        return packet/'manifest.json'
    manifest=Path(manifest).resolve();target=default_exchange()/manifest.parent.name
    if manifest.parent==target.resolve():return manifest
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if (target/'manifest.json').is_file() and (target/'manifest.json').read_bytes()==manifest.read_bytes():return target/'manifest.json'
        target=target.with_name(target.name+'_'+uuid.uuid4().hex[:6])
    staging=target.with_name(target.name+'.partial_'+uuid.uuid4().hex[:6])
    shutil.copytree(manifest.parent,staging);staging.rename(target)
    return target/'manifest.json'

def plan_from_manifest(manifest):
    manifest=Path(manifest);data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    by_name={};conflicts=set()
    for entry in data['materials'].values():
        name=entry['name']
        if name in by_name and by_name[name]!=entry:conflicts.add(name)
        by_name[name]=entry
    plan=[];unmatched=[];missing=[];locked=[]
    for node in hou.node('/').allSubChildren():
        if node.type().name()!='mtlximage' or not node.parm('file'):continue
        builder=node.parent();name=builder.userData('b2h_source_material') or builder.comment()
        if not name:continue
        role=node.userData('b2h_role') or node.name();entry=by_name.get(name)
        if not entry or name in conflicts:
            if not Path(node.parm('file').eval()).is_file():unmatched.append(name)
            continue
        texture=entry.get('maps',{}).get(role)
        if not texture:continue
        file=(manifest.parent/texture['path']).resolve()
        if not file.is_file():missing.append(str(file));continue
        if node.parm('file').isLocked() or node.parm('file').keyframes():locked.append(node.path());continue
        space='sRGB' if role in ('base_color','emission') and texture.get('colorspace')=='sRGB' else 'raw'
        plan.append((node,file,space))
    return plan,{'unmatched_materials':sorted(set(unmatched)),'missing_source_files':sorted(set(missing)),'locked_or_animated_nodes':locked,'ambiguous_materials':sorted(conflicts)}

def reconnect_manifest(manifest):
    manifest=local_package(manifest);plan,report=plan_from_manifest(manifest)
    with hou.undos.group('BCGI Reconnect Textures Only'):
        for node,file,space in plan:
            node.parm('file').set(file.as_posix())
            if node.parm('filecolorspace'):node.parm('filecolorspace').set(space)
    report.update({'updated_image_nodes':len(plan),'manifest':str(manifest),'geometry_changed':False})
    atomic_json(default_exchange()/'texture_reconnect_report.json',report)
    if hou.isUIAvailable():hou.ui.setStatusMessage('Blender2Houdini: updated %d texture nodes; %d unmatched materials'%(len(plan),len(report['unmatched_materials'])))
    return report

def reconnect_folder(folder):
    folder=Path(folder).resolve();manifests=list(folder.rglob('manifest.json'))
    if (folder/'manifest.json').exists():manifests.append(folder/'manifest.json')
    pointer=folder/'latest.json'
    if pointer.exists():
        info=json.loads(pointer.read_text());file=Path(info['manifest'])
        if not file.exists() and info.get('relative_manifest'):file=folder/info['relative_manifest']
        if file.exists():return reconnect_manifest(file)
    if manifests:return reconnect_manifest(max(manifests,key=lambda p:p.stat().st_mtime_ns))
    files={}
    for file in folder.rglob('*'):
        if file.is_file():files.setdefault(file.name,[]).append(file)
    plan=[];ambiguous=[];missing=[]
    for node in hou.node('/').allSubChildren():
        if node.type().name()!='mtlximage' or not node.parm('file'):continue
        parm=node.parm('file')
        if Path(parm.eval()).is_file():continue
        found=files.get(Path(parm.eval()).name,[])
        if len(found)==1 and not parm.isLocked() and not parm.keyframes():plan.append((parm,found[0]))
        elif len(found)>1:ambiguous.append(node.path())
        else:missing.append(node.path())
    with hou.undos.group('BCGI Relink Texture Folder'):
        target=default_exchange()/project_name(Path(hou.hipFile.path()).stem+'.blend');target.mkdir(parents=True,exist_ok=True)
        for parm,source in plan:
            dest=copy_named(source,target)
            parm.set(dest.as_posix())
    report={'updated_image_nodes':len(plan),'ambiguous_nodes':ambiguous,'missing_nodes':missing,'geometry_changed':False}
    atomic_json(default_exchange()/'texture_reconnect_report.json',report);return report

def choose_folder():
    folder=hou.ui.selectFile(title='Choose Exchange or Texture Folder',file_type=hou.fileType.Directory,chooser_mode=hou.fileChooserMode.Read)
    if not folder:return
    report=reconnect_folder(hou.expandString(folder));hou.ui.setStatusMessage('Blender2Houdini: reconnected %d texture nodes'%report['updated_image_nodes']);return report
