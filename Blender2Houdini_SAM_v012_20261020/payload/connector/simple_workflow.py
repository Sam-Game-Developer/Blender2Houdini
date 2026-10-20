"""SAM: one editable OBJ Geometry per source mesh, direct Solaris controls."""
import hou,json,re
from pathlib import Path

def safe(value):
    value=re.sub(r'[^A-Za-z0-9_]', '_',value)
    return 'asset_'+value if value[:1].isdigit() else value

def organize(asset):
    if asset.userData('b2h_simple_workflow')=='1':
        for node in hou.node('/stage').children():
            if node.userData('b2h_managed_stage'):node.setUserData('b2h_managed_stage',asset.path())
        return hou.node('/stage/OUT_FINAL_STAGE')
    top=hou.node('/stage');obj=hou.node('/obj')
    data=json.loads(Path(asset.userData('b2h_manifest')).read_text())
    from sop_layout import capture
    sop_saved=capture(data)
    lib=next(n for n in asset.allSubChildren() if n.type().name()=='materiallibrary')
    assign=next(n for n in asset.allSubChildren() if n.type().name()=='assignmaterial')
    incoming_material_paths={mid:lib.parm('matpath%d'%i).eval() for i,mid in enumerate(data['materials'],1)}
    global_lib=top.node('MATERIAL_LIBRARY')
    tag=safe(Path(asset.userData('b2h_manifest')).parent.name)
    shader_names={mid:tag+'_'+mid if global_lib and global_lib!=lib else mid for mid in data['materials']}
    bypart={n.userData('b2h_partname'):n for n in asset.allSubChildren() if n.type().name()=='sopimport' and n.userData('b2h_partname')}
    sources={};part_sops={};primitive_paths={};roots=set()
    for part in data['parts']:sources.setdefault(part['source'],[]).append(part)
    # Source backups remain hidden. The editable containers have source names.
    for old in obj.children():
        if old.userData('b2h_manifest') and not old.userData('b2h_live_geometry') and not old.userData('b2h_asset_root'):old.setDisplayFlag(False)
    records={r['name']:r for r in data.get('objects',[])}
    def logical_path(name):
        parent=records.get(name,{}).get('parent')
        return (logical_path(parent)+'/' if parent in records else '')+safe(name)
    from collection_workflow import create_containers
    geometries,world_holders,part_sops,primitive_paths=create_containers(asset,data,shader_names,bypart)
    # Keep hidden source/cook helpers in one backend, never one subnet per car.
    backend=obj.node('B2H_SOURCE_DATA') or obj.createNode('subnet','B2H_SOURCE_DATA')
    backend.setDisplayFlag(False)
    mappings=[]
    owned=[n for n in obj.children() if n!=backend and not n.userData('b2h_live_geometry') and not n.userData('b2h_asset_root') and (n.userData('b2h_manifest') or n.userData('b2h_category'))]
    for root in owned:
        oldpath=root.path();moved=hou.moveNodesTo((root,),backend)[0];moved.setDisplayFlag(False)
        mappings.append((oldpath,moved.path()))
    # Explicitly repair source references after hiding all old helper containers.
    for node in hou.node('/').allSubChildren():
        for key in ['objpath1','soppath']:
            parm=node.parm(key)
            if not parm:continue
            value=parm.eval()
            for oldpath,newpath in mappings:
                if value==oldpath or value.startswith(oldpath+'/'):
                    parm.set(newpath+value[len(oldpath):]);break
    updated=[]
    for name,holder,om in world_holders:
        target=next(newpath for previous,newpath in mappings if previous.rsplit('/',1)[-1]=='B2H_USD_'+safe(name))
        node=hou.node(target);updated.append((name,node,node.node('WORLD_GEOMETRY')))
    world_holders=updated
    archive=top.node('B2H_PREVIOUS_IMPORTS') or top.createNode('subnet','B2H_PREVIOUS_IMPORTS')
    archive.setDisplayFlag(False)
    # Accumulate unique MaterialX definitions in one shared library.
    if global_lib and global_lib!=lib:
        count=global_lib.parm('materials').eval()
        global_lib.parm('materials').set(count+len(data['materials']))
        for offset,mid in enumerate(data['materials'],1):
            shader=lib.node(mid);shader.setName(shader_names[mid])
            shader=hou.moveNodesTo((shader,),global_lib)[0]
            global_lib.parm('matnode%d'%(count+offset)).set(shader.name())
            global_lib.parm('matpath%d'%(count+offset)).set(incoming_material_paths[mid])
        hou.moveNodesTo((lib,),archive);lib=global_lib
    else:
        lib=hou.moveNodesTo((lib,),top)[0];lib.setName('MATERIAL_LIBRARY')
    global_assign=top.node('ASSIGN_MATERIALS')
    old_bindings=[]
    if global_assign and global_assign!=assign:
        prefixes=list({'/World/PROPS/'+safe(records.get(name,{}).get('asset_name',name)) for name in sources}) if data.get('collection_layout') else ['/World/PROPS/'+logical_path(name) for name in sources]
        for i in range(1,global_assign.parm('nummaterials').eval()+1):
            pattern=global_assign.parm('primpattern%d'%i).eval();base=pattern.split()[0]
            if not any(base==prefix or base.startswith(prefix+'/') for prefix in prefixes):
                old_bindings.append((pattern,global_assign.parm('matspecpath%d'%i).eval()))
        hou.moveNodesTo((assign,),archive);assign=global_assign
    else:
        assign=hou.moveNodesTo((assign,),top)[0];assign.setName('ASSIGN_MATERIALS')
    lib.setUserData('b2h_simple','1');assign.setUserData('b2h_simple','1')
    for node in list(top.children()):
        if node.type().name()=='switch' and node.userData('b2h_shot')=='1':node.destroy()
    merge=top.node('MERGE_ASSETS') or top.createNode('merge','MERGE_ASSETS')
    for i in reversed(range(len(merge.inputs()))):merge.setInput(i,None)
    for index,(name,holder,om) in enumerate(world_holders):
        imp=next((n for n in top.children() if n.type().name()=='sopimport' and n.userData('b2h_source')==name),None) or top.createNode('sopimport','IMPORT_'+safe(name))
        imp.setUserData('b2h_simple','1');imp.setUserData('b2h_source',name)
        imp.parm('soppath').set(om.path());imp.parm('primpath').set('/World/PROPS/'+logical_path(name))
        imp.parm('enable_pathattr').set(1);imp.parm('pathattr').set('path')
        imp.parm('pathprefix').set('/World/PROPS');imp.setPosition(hou.Vector2(index*4,4));
    imports=[n for n in top.children() if n.type().name()=='sopimport' and n.userData('b2h_simple')=='1']
    for i,imp in enumerate(imports):merge.setInput(i,imp);imp.setPosition(hou.Vector2(i*4,4))
    lib.setInput(0,merge);assign.setInput(0,lib)
    bindings=old_bindings+[(primitive_paths[p['name']]+' '+primitive_paths[p['name']]+'/**',incoming_material_paths[p['material']]) for p in data['parts']]
    assign.parm('nummaterials').set(len(bindings))
    for i,(pattern,material) in enumerate(bindings,1):
        assign.parm('primpattern%d'%i).set(pattern);assign.parm('matspecpath%d'%i).set(material)
    light=top.node('04_LIGHTING_DOME');new_light=light is None
    if not light:
        dome=next(n for n in asset.allSubChildren() if n.type().name().split('::')[0]=='domelight')
        light=hou.moveNodesTo((dome,),top)[0];light.setName('04_LIGHTING_DOME')
    if new_light or light.input(0) is None:light.setInput(0,assign)
    camera=top.node('05_CAMERA')
    if camera is None:
        camera=top.createNode('camera','05_CAMERA');camera.parm('primpath').set('/cameras/B2H_RENDER_CAMERA');camera.setInput(0,light)
        import math
        boxes=[om.geometry().boundingBox() for name,holder,om in world_holders if om.geometry().prims()]
        if boxes:
            low=[min(b.minvec()[i] for b in boxes) for i in range(3)];high=[max(b.maxvec()[i] for b in boxes) for i in range(3)]
            center=[(a+b)/2 for a,b in zip(low,high)];size=max(max(b-a for a,b in zip(low,high)),.1)
            camera.parmTuple('t').set((center[0]+size*.85,center[1]+size*.5,center[2]+size*1.3))
            camera.parmTuple('r').set((-math.degrees(math.atan2(.5,math.hypot(.85,1.3))),math.degrees(math.atan2(.85,1.3)),0))
    settings=top.node('06_KARMA_RENDER_SETTINGS')
    if settings is None:
        settings=top.createNode('karma','06_KARMA_RENDER_SETTINGS');settings.setInput(0,camera);settings.parm('camera').set('/cameras/B2H_RENDER_CAMERA')
    settings.parm('engine').set('xpu')
    final=top.node('OUT_FINAL_STAGE') or top.createNode('null','OUT_FINAL_STAGE');final.setInput(0,settings)
    rop=top.node('USD_RENDER_ROP') or top.createNode('usdrender_rop','USD_RENDER_ROP');rop.parm('loppath').set(final.path())
    # Previous generated Stage subnets are archived, not rendered or lost.
    for node in list(top.children()):
        if node!=archive and node.type().name()=='subnet' and node.userData('b2h_verified')=='1':
            was_active=node.path()==asset.path()
            moved=hou.moveNodesTo((node,),archive)[0]
            if was_active:asset=moved
    asset.setUserData('b2h_simple_workflow','1');asset.setUserData('b2h_material_library',lib.path())
    material_nodes={mid:lib.node(shader_names[mid]).path() for mid in data['materials']}
    asset.setUserData('b2h_material_nodes',json.dumps(material_nodes))
    for name in sources:
        geometries[name].setUserData('b2h_material_nodes',json.dumps(material_nodes))
        geometries[name].setUserData('b2h_builder',data.get('material_builder','karma'))
    asset.setUserData('b2h_part_sops',json.dumps(part_sops));asset.setUserData('b2h_preview_node',final.path())
    for i,node in enumerate([merge,lib,assign,light,camera,settings,final]):
        node.setPosition(hou.Vector2(8,2-i*2));node.setUserData('b2h_managed_stage',asset.path())
    rop.setPosition(hou.Vector2(12,-10));archive.setPosition(hou.Vector2(-4,4))
    final.setUserData('b2h_global_assembly','1');merge.setUserData('b2h_global_assembly','1')
    for i,car in enumerate(n for n in obj.children() if n.userData('b2h_live_geometry')):car.setPosition(hou.Vector2(i*4,0))
    backend.setPosition(hou.Vector2(-4,-3))
    from scene_extras import apply as apply_scene_extras
    apply_scene_extras(data,light,camera,settings)
    from sop_layout import apply as apply_sop_layout
    apply_sop_layout(data,sop_saved)
    final.setDisplayFlag(True)
    return asset,final
