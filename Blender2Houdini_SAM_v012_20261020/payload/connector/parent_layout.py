"""Native OBJ Null/Geometry parenting for Blender Empty hierarchies."""
import hou,json,hashlib
from pathlib import Path
from collection_workflow import safe,converted_matrix

def apply(data):
    if data.get('parent_layout')!='objects':return
    records={r['name']:r for r in data.get('objects',[])}
    for wrapper in hou.node('/obj').children():
        asset_name=wrapper.userData('b2h_asset_root');aggregate=wrapper.node('GEOMETRY')
        if not asset_name or aggregate is None:continue
        parts=[p for p in data['parts'] if records.get(p['source'],{}).get('asset_name',p['source'])==asset_name]
        if not parts:continue
        manifest=Path(aggregate.userData('b2h_manifest'));cache=manifest.parent/'native_geometry';cache.mkdir(exist_ok=True)
        original_sops=json.loads(aggregate.userData('b2h_part_sops'));materials=aggregate.userData('b2h_material_nodes')
        names={p['source'] for p in parts};needed=set(names)
        for name in list(names):
            parent=records[name].get('parent');seen=set()
            while parent in records and parent not in seen:seen.add(parent);needed.add(parent);parent=records[parent].get('parent')
        # Cache in each mesh's own coordinate system; world transforms live on OBJs.
        cached={}
        for part in parts:
            sop=hou.node(original_sops[part['name']]);g=hou.Geometry();g.merge(sop.geometry())
            if not g.prims() or sop.errors():raise ValueError('Empty source part '+part['source'])
            transform=converted_matrix(records[part['source']]['matrix_world'],data.get('unit_scale',1))
            g.transform(aggregate.worldTransform()*wrapper.worldTransform().inverted()*transform.inverted())
            dest=cache/(safe(part['name'])+'.bgeo.sc');g.saveToFile(str(dest));cached[part['name']]=dest
        source=wrapper.node('SOURCE_DATA');archive=source.node('PARENT_INPUT_ARCHIVE') or source.createNode('subnet','PARENT_INPUT_ARCHIVE');archive.setDisplayFlag(False)
        for node in [aggregate,wrapper.node('CONTROLS')]:
            if node is None:continue
            for tag in ['b2h_live_geometry','b2h_collection_container']:
                if node.userData(tag):node.destroyUserData(tag)
            moved=hou.moveNodesTo((node,),archive)[0];moved.setDisplayFlag(False)
        objects={}
        def depth(name):
            count=0;seen=set()
            while name in records and name not in seen:seen.add(name);name=records[name].get('parent');count+=1
            return count
        for name in sorted(needed,key=lambda name:(depth(name),records[name].get('order',0))):
            rec=records[name];is_mesh=name in names
            node=next((n for n in wrapper.children() if n.userData('b2h_native_name')==name),None)
            fresh=node is None
            if fresh:node=wrapper.createNode('geo' if is_mesh else 'null',safe(name))
            node.setUserData('b2h_native_name',name);node.setUserData('blender_name',name)
            node.setUserData('b2h_manifest',str(manifest));node.setUserData('b2h_source_parent',rec.get('parent') or '')
            objects[name]=node;parent=objects.get(rec.get('parent'));node.setInput(0,parent)
            rest=converted_matrix(rec['matrix_world'],data.get('unit_scale',1))
            parent_rest=converted_matrix(records[rec['parent']]['matrix_world'],data.get('unit_scale',1)) if parent else hou.hmath.identityTransform()
            if fresh:
                node.parmTuple('t').set((0,0,0));node.parmTuple('r').set((0,0,0));node.parmTuple('s').set((1,1,1))
            node.setPreTransform(rest*parent_rest.inverted())
            node.setColor(hou.Color((.15,.45,.65) if is_mesh else (.9,.65,.15)))
            if is_mesh:
                for child in node.children():child.destroy()
                node.setUserData('b2h_live_geometry',name);node.setUserData('b2h_collection_container','1')
                node.setUserData('b2h_native_part','1');node.setUserData('b2h_material_nodes',materials)
                node.setUserData('b2h_builder',data.get('material_builder','karma'))
        # Source nodes belonging to a previous hierarchy remain recoverable.
        for node in list(wrapper.children()):
            old_name=node.userData('b2h_native_name')
            if old_name and old_name not in needed:
                if node.userData('b2h_live_geometry'):node.destroyUserData('b2h_live_geometry')
                old=hou.moveNodesTo((node,),archive)[0];old.setDisplayFlag(False)
        part_sops={};by_source={name:[] for name in names}
        for part in parts:
            node=objects[part['source']];file=node.createNode('file',safe(part['material']))
            file.parm('file').set(cached[part['name']].as_posix())
            assign=node.createNode('attribwrangle','MATERIAL_'+safe(part['material']));assign.setInput(0,file);assign.parm('class').set('primitive')
            assign.parm('snippet').set('s@shop_materialpath='+json.dumps(json.loads(materials)[part['material']])+';')
            assign.setUserData('b2h_partname',part['name'])
            part_sops[part['name']]=assign.path();by_source[part['source']].append(assign)
        for name,nodes in by_source.items():
            geo=objects[name];merge=geo.createNode('merge','MERGE_MATERIALS')
            for i,n in enumerate(nodes):merge.setInput(i,n)
            out=geo.createNode('null','OUT_MESH');out.setInput(0,merge);out.setDisplayFlag(True);out.setRenderFlag(True)
            geo.setDisplayFlag(True);geo.setUserData('b2h_part_sops',json.dumps({p['name']:part_sops[p['name']] for p in parts if p['source']==name}));geo.layoutChildren()
        stage_geo=source.node('NATIVE_STAGE') or source.createNode('geo','NATIVE_STAGE')
        for n in stage_geo.children():n.destroy()
        stage_geo.setDisplayFlag(False);merge=stage_geo.createNode('merge','MERGE_ASSET')
        for i,name in enumerate(sorted(names)):
            om=stage_geo.createNode('object_merge',safe(name));om.parm('objpath1').set(objects[name].node('OUT_MESH').path());om.parm('xformtype').set(1);merge.setInput(i,om)
        export=stage_geo.createNode('attribwrangle','EXPORT_WORLD');export.setInput(0,merge);export.parm('class').set('point')
        export.parm('snippet').set('matrix m=optransform('+json.dumps(stage_geo.path())+'); @P *= m; if(haspointattrib(0,"N")) @N=normalize(@N * transpose(invert(matrix3(m))));')
        normals=stage_geo.createNode('attribwrangle','EXPORT_NORMALS');normals.setInput(0,export);normals.parm('class').set('vertex')
        normals.parm('snippet').set('matrix m=optransform('+json.dumps(stage_geo.path())+'); if(hasvertexattrib(0,"N")) @N=normalize(@N * transpose(invert(matrix3(m))));');normals.setDisplayFlag(True);normals.setRenderFlag(True)
        stage_geo.setUserData('b2h_manifest',str(manifest));stage_geo.layoutChildren()
        imp=next(n for n in hou.node('/stage').children() if n.type().name()=='sopimport' and n.userData('b2h_source')==asset_name)
        imp.parm('soppath').set(normals.path());imp.setUserData('b2h_asset_geometry',wrapper.path())
        wrapper.setUserData('b2h_parent_layout','objects');wrapper.setUserData('b2h_part_sops',json.dumps(part_sops))
        for n in hou.node('/stage').allSubChildren():
            if n.userData('b2h_manifest')==str(manifest) and n.userData('b2h_verified')=='1':n.setUserData('b2h_part_sops',json.dumps(part_sops))
        wrapper.setComment('SAM v012 | Native parenting | '+str(len(names))+' meshes');wrapper.layoutChildren()
        source.setPosition(hou.Vector2(-6,-4))
        wrapper.setDisplayFlag(True)
