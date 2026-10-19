from bridge_config import default_exchange
"""Blender2Houdini SAM v001 20261008. Static FBX + MaterialX importer."""
import hou, json, os, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent
EXTRA_PBR={'coat':'coat','coat_roughness':'coat_roughness','coat_ior':'coat_IOR','anisotropy':'specular_anisotropy','anisotropy_rotation':'specular_rotation','sheen':'sheen','sheen_roughness':'sheen_roughness','subsurface':'subsurface','subsurface_scale':'subsurface_scale','diffuse_roughness':'diffuse_roughness'}
def portable(path):
    p = Path(path).resolve()
    return p.as_posix()
def import_latest(exchange=None):
    import builtins
    exchange=Path(exchange or default_exchange())
    exchange.mkdir(parents=True,exist_ok=True)
    if hou.isUIAvailable():
        state=getattr(builtins,'_b2h_auto_state',None)
        if not state or Path(state['folder']).resolve()!=exchange.resolve():
            import auto_import_bridge
            auto_import_bridge.start(exchange)
    manifest=None
    try:
        info=json.loads((exchange/'latest.json').read_text(encoding='utf-8'))
        manifest=Path(info['manifest'])
        if not manifest.exists():manifest=exchange/manifest.parent.name/'manifest.json'
        import auto_import_bridge
        status=auto_import_bridge.dispatch_manifest(manifest)
        stage=hou.node(status['stage']) if status.get('stage') else None
    except Exception as error:
        status={'manifest':str(manifest) if manifest else '', 'ok':False,'message':str(error)}
        temp=exchange/'houdini_status.tmp';temp.write_text(json.dumps(status,indent=2),encoding='utf-8');os.replace(temp,exchange/'houdini_status.json')
        raise
    temp=exchange/'houdini_status.tmp';temp.write_text(json.dumps(status,indent=2),encoding='utf-8');os.replace(temp,exchange/'houdini_status.json')
    return stage

def focus_result(stage):
    import preview_bridge
    return preview_bridge.focus(stage)
    return
    out = stage.node('OUT_KARMA')
    out.setDisplayFlag(True)
    stage.setDisplayFlag(True)
    out.setSelected(True, clear_all_selected=True)
    if hou.isUIAvailable():
        for pane in hou.ui.paneTabs():
            if isinstance(pane, hou.NetworkEditor): pane.setPwd(stage); pane.homeToSelection()
            if isinstance(pane, hou.SceneViewer): pane.setPwd(stage); pane.curViewport().frameAll()
        hou.ui.setStatusMessage(stage.userData('b2h_status') or 'Blender2Houdini imported', hou.severityType.Message)
def import_manifest(manifest):
    manifest = Path(manifest); data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('schema') != 'Blender2Houdini-1': raise ValueError('Unsupported package schema')
    from material_builders import validate_mode
    validate_mode(data.get('material_builder','karma'))
    package = manifest.parent
    for mat in data['materials'].values():
        for tex in mat['maps'].values():
            if not (package / tex['path']).is_file(): raise ValueError('Missing texture: ' + tex['path'])
    fbx = package / data['fbx']
    if not fbx.is_file(): raise ValueError('Missing FBX')
    objroot, messages = hou.hipFile.importFBX(str(fbx), suppress_save_prompt=True, merge_into_scene=True, import_cameras=False, import_lights=False, import_animation=False, import_materials=False, override_scene_frame_range=False, convert_units=True)
    objroot.setName('Blender2Houdini_MESH', unique_name=True)
    objroot.setUserData('b2h_manifest', str(manifest))
    for n in objroot.allSubChildren():
        if n.type().name() == 'file' and n.parm('file'):
            value = n.parm('file').eval()
            suffix = '#' + value.split('#', 1)[1] if '#' in value else ''
            n.parm('file').set(portable(fbx) + suffix)
    # FBX is exported Y-up in Blender. Keep that coordinate system and metre values.
    stage = hou.node('/stage').createNode('subnet', 'Blender2Houdini_KARMA')
    stage.setUserData('b2h_manifest', str(manifest))
    last = None; prims = []
    geos = [n for n in objroot.allSubChildren() if n.type().name() == 'geo']
    for part in data['parts']:
        partname=re.sub(r'[^A-Za-z0-9_]', '_', part['name'])
        candidates = [n for n in geos if n.name() == partname]
        if len(candidates) != 1: raise ValueError('FBX part not found uniquely: ' + part['name'])
        geo = candidates[0]
        holder = hou.node('/obj').createNode('geo','B2H_WORLD_' + part['name'])
        for c in holder.children(): c.destroy()
        om = holder.createNode('object_merge','FBX_WORLD')
        om.parm('objpath1').set(geo.displayNode().path()); om.parm('xformtype').set(1)
        om.setDisplayFlag(True); om.setRenderFlag(True)
        holder.setDisplayFlag(False); holder.setUserData('b2h_manifest',str(manifest))
        prim = '/Blender2Houdini/' + stage.name() + '/' + partname
        imp = stage.createNode('sopimport',partname)
        imp.setUserData('b2h_partname',part['name'])
        if last: imp.setInput(0,last)
        imp.parm('soppath').set(om.path()); imp.parm('primpath').set(prim)
        imp.parm('pathprefix').set(prim)
        last = imp; prims.append((prim,part['material']))
        g=om.geometry()
        if om.errors() or not g.prims(): raise ValueError('Empty or failed FBX geometry: ' + part['name'])
        if len(g.prims()) != part['faces']: raise ValueError('Face count changed: ' + part['name'])
    lib=stage.createNode('materiallibrary','PBR_MATERIALX')
    lib.setInput(0,last)
    lib.parm('materials').set(len(data['materials']))
    prefix='/materials/' + stage.name() + '/'
    lib.parm('matpathprefix').set(prefix)
    for i,(mid,mat) in enumerate(data['materials'].items(),1):
        from material_builders import build_material
        sub=build_material(lib,mid,mat,package,data.get('material_builder','karma'))
        lib.parm('matnode%d'%i).set(mid); lib.parm('matpath%d'%i).set(prefix+mid)
    lib.layoutChildren()
    assign=stage.createNode('assignmaterial','ASSIGN_PBR'); assign.setInput(0,lib)
    assign.parm('nummaterials').set(len(prims))
    for i,(prim,mid) in enumerate(prims,1):
        assign.parm('primpattern%d'%i).set(prim+'/**')
        assign.parm('matspecpath%d'%i).set(prefix+mid)
    out=stage.createNode('null','OUT_KARMA');out.setInput(0,assign);out.setDisplayFlag(True)
    stage.setDisplayFlag(True);stage.layoutChildren()
    out.cook(force=True)
    if out.errors(): raise ValueError(str(out.errors()))
    status='IMPORTED: %d mesh parts, %d %s materials' % (len(prims),len(data['materials']),data.get('material_builder','karma'))
    stage.setComment(status); stage.setGenericFlag(hou.nodeFlag.DisplayComment,True)
    stage.setUserData('b2h_status',status)
    stage.setUserData('b2h_verified','1')
    stage=focus_result(stage)
    if messages: print(messages)
    if data['warnings']: print('WARNINGS:',data['warnings'])
    print(status, stage.path())
    return stage
def install_shelf():
    shelfpath=str(ROOT / 'Blender2Houdini.shelf')
    script="import sys\nfrom pathlib import Path\np = Path(" + repr(str(ROOT)) + ")\nsys.path.insert(0,str(p))\nimport houdini_importer\nimport importlib\nimportlib.reload(houdini_importer)\ntry:\n houdini_importer.import_latest()\nexcept Exception as e:\n hou.ui.setStatusMessage('Blender2Houdini ERROR: '+str(e), hou.severityType.Error)"
    tool=hou.shelves.tools().get('b2h_import_sam_v001') or hou.shelves.newTool(file_path=shelfpath,name='b2h_import_sam_v001',label='Import Blender PBR',script=script,icon=str(ROOT/'icons'/'blender.png'),help='Import latest Blender2Houdini package with Karma MaterialX materials')
    shelf=hou.shelves.shelves().get('b2h_sam_v001') or hou.shelves.newShelf(file_path=shelfpath,name='b2h_sam_v001',label='Blender2Houdini SAM v008')
    shelf.setLabel('Blender2Houdini SAM v008')
    send_script="import sys, importlib, hou\nfrom pathlib import Path\nroot=Path("+repr(str(ROOT))+")\nsys.path.insert(0,str(root))\nimport houdini_exporter\nimportlib.reload(houdini_exporter)\ntry:\n houdini_exporter.send_selected()\nexcept Exception as e:\n hou.ui.setStatusMessage('Blender2Houdini ERROR: '+str(e), hou.severityType.Error)"
    send=hou.shelves.tools().get('b2h_send_sam_v001') or hou.shelves.newTool(file_path=shelfpath,name='b2h_send_sam_v001',label='Send to Blender',script=send_script,icon=str(ROOT/'icons'/'blender.png'))
    tool.setScript(script);send.setScript(send_script)
    actions=[]
    for mode,label in [('karma','Use Karma'),('materialx','Use MaterialX')]:
        action_script="import sys,importlib,hou\nsys.path.insert(0,"+repr(str(ROOT))+")\nimport material_builders\nimportlib.reload(material_builders)\ntry:\n material_builders.use_selected("+repr(mode)+")\nexcept Exception as e:\n hou.ui.setStatusMessage('Blender2Houdini ERROR: '+str(e),hou.severityType.Error)"
        name='b2h_use_'+mode+'_sam'
        action=hou.shelves.tools().get(name) or hou.shelves.newTool(file_path=shelfpath,name=name,label=label,script=action_script,icon=str(ROOT/'icons'/'blender.png'))
        action.setScript(action_script);actions.append(action)
    shelf.setTools((tool,send,*actions))
    sets=hou.shelves.shelfSets()
    for name in list(sets):
        if name in sets:
            ss=sets[name]
            retained=tuple(s for s in ss.shelves() if 'blender2houdini' not in s.label().lower().replace(' ','') and not s.name().startswith('b2h_'))
            ss.setShelves(retained+((shelf,) if name in ['shelf_set_1','solaris_1'] else ()))
    for key,old in list(hou.shelves.shelves().items()):
        if key!=shelf.name() and (key.startswith('b2h_') or 'blender2houdini' in old.label().lower().replace(' ','')):old.destroy()
    for key,old in list(hou.shelves.tools().items()):
        if key.startswith('b2h_') and key not in [t.name() for t in shelf.tools()]:old.destroy()
    return shelf
if __name__=='__main__': install_shelf()
