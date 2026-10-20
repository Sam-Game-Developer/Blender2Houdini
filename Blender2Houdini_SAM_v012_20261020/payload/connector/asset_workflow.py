"""Asset-level organization and rigid EMPTY-parent controls. No skin/driver solver."""
import hou,json
from collection_workflow import safe,converted_matrix

def repair_paths(mappings):
    mappings=sorted(mappings,key=lambda pair:len(pair[0]),reverse=True)
    def replace(value):
        if any(value==new or value.startswith(new+'/') for old,new in mappings):return value
        for old,new in mappings:
            if value==old or (value.startswith(old+'/') and not value.startswith(new+'/')):
                return new+value[len(old):]
        return value
    def walk(value):
        if isinstance(value,str):return replace(value)
        if isinstance(value,dict):return {k:walk(v) for k,v in value.items()}
        if isinstance(value,list):return [walk(v) for v in value]
        return value
    for n in hou.node('/').allSubChildren():
        for key in ['objpath1','soppath','loppath']:
            p=n.parm(key)
            if p and not p.keyframes():
                value=p.eval();changed=replace(value)
                if changed!=value:p.set(changed)
        for key in ['b2h_part_sops','b2h_material_nodes','b2h_preview_node']:
            value=n.userData(key)
            if not value:continue
            if key=='b2h_preview_node':n.setUserData(key,replace(value));continue
            try:n.setUserData(key,json.dumps(walk(json.loads(value))))
            except (ValueError,TypeError):pass

def _source_roots(car,holder,backend):
    found=set();pending=[car,holder]
    while pending:
        root=pending.pop()
        for n in (root,)+root.allSubChildren():
            for key in ['objpath1','soppath']:
                p=n.parm(key)
                target=hou.node(p.eval()) if p and p.eval() else None
                if not target:continue
                while target.parent() and target.parent()!=backend and target.path()!='/obj':target=target.parent()
                if target.parent()==backend and target not in found:found.add(target);pending.append(target)
    if holder.parent()==backend:found.add(holder)
    return found

def organize(data):
    obj=hou.node('/obj');backend=obj.node('B2H_SOURCE_DATA');records={r['name']:r for r in data.get('objects',[])}
    asset_names=list(dict.fromkeys(records.get(p['source'],{}).get('asset_name',p['source']) for p in data['parts']))
    results=[]
    for asset_name in asset_names:
        car=next((n for n in obj.allSubChildren() if n.userData('b2h_collection_container')=='1' and n.userData('b2h_live_geometry')==asset_name),None)
        if not car:continue
        wrapper=next((n for n in obj.children() if n.userData('b2h_asset_root')==asset_name),None)
        mappings=[]
        if not wrapper:
            old=car.path();world=car.worldTransform();car.setName(safe(asset_name)+'_GEOMETRY_MOVING',unique_name=True);temporary=car.path()
            wrapper=obj.createNode('subnet',safe(asset_name));wrapper.setUserData('b2h_asset_root',asset_name)
            car=hou.moveNodesTo((car,),wrapper)[0];car.setName('GEOMETRY');car.setWorldTransform(world)
            mappings.extend([(old,car.path()),(temporary,car.path())])
        if car.parent()!=wrapper:
            old=car.path();world=car.worldTransform()*wrapper.worldTransform();car=hou.moveNodesTo((car,),wrapper)[0];car.setName('GEOMETRY');car.setWorldTransform(world);mappings.append((old,car.path()))
        wrapper.setUserData('b2h_manifest',car.userData('b2h_manifest'));wrapper.setColor(hou.Color((0.15,0.45,0.65)))
        controls=wrapper.node('CONTROLS') or wrapper.createNode('subnet','CONTROLS')
        source=wrapper.node('SOURCE_DATA') or wrapper.createNode('subnet','SOURCE_DATA');source.setDisplayFlag(False)
        holder=next((n for n in (backend.allSubChildren() if backend else ()) if n.name().startswith('B2H_USD_'+safe(asset_name)) and n.userData('b2h_manifest')==car.userData('b2h_manifest')),None)
        if not holder:
            holder=next((n for n in source.children() if n.userData('b2h_world_holder')==asset_name),None)
        if holder and backend and holder.parent()==backend:
            # Source transforms are preserved; references are repaired explicitly.
            roots=_source_roots(car,holder,backend)
            source_records=[(n,n.path(),n.worldTransform(),n==holder) for n in roots]
            for n,old,world,is_holder in source_records:
                moved=hou.moveNodesTo((n,),source)[0];moved.setWorldTransform(world)
                mappings.append((old,moved.path()))
                if is_holder:holder=moved
        repair_paths(mappings)
        names={p['source'] for p in data['parts'] if records.get(p['source'],{}).get('asset_name',p['source'])==asset_name}
        needed=set()
        for name in names:
            parent=records.get(name,{}).get('parent');visited=set()
            while parent in records and parent not in visited:
                visited.add(parent)
                if records[parent].get('type')=='EMPTY':needed.add(parent)
                parent=records[parent].get('parent')
        legacy=[n for n in obj.children() if n.name() in needed and n.type().name()=='null']
        if legacy:
            oldpaths=[n.path() for n in legacy];worlds=[n.worldTransform() for n in legacy]
            moved=hou.moveNodesTo(tuple(legacy),controls)
            for old,world,n in zip(oldpaths,worlds,moved):n.setWorldTransform(world);mappings.append((old,n.path()))
        control_nodes={}
        def depth(name):
            count=0;seen=set()
            while name in records and name not in seen:seen.add(name);name=records[name].get('parent');count+=1
            return count
        for name in sorted(needed,key=lambda name:(depth(name),records[name].get('order',0))):
            node=next((n for n in controls.children() if n.userData('b2h_control_source')==name or n.name()==safe(name)),None)
            if node is None:node=controls.createNode('null',safe(name))
            fresh=node.userData('b2h_control_source') is None
            node.setUserData('b2h_control_source',name);control_nodes[name]=node
            parent=records[name].get('parent');visited=set()
            while parent in records and parent not in needed and parent not in visited:visited.add(parent);parent=records[parent].get('parent')
            rest=converted_matrix(records[name]['matrix_world'],data.get('unit_scale',1))
            parent_node=control_nodes.get(parent)
            if node.input(0)!=parent_node:node.setInput(0,parent_node)
            parent_rest=converted_matrix(records[parent]['matrix_world'],data.get('unit_scale',1)) if parent in needed else hou.hmath.identityTransform()
            if fresh:
                node.parmTuple('t').set((0,0,0));node.parmTuple('r').set((0,0,0));node.parmTuple('s').set((1,1,1))
            node.setPreTransform(rest*parent_rest.inverted())
            node.setUserData('b2h_rest_world',json.dumps(list(rest.asTuple())))
            node.setColor(hou.Color((0.9,0.65,0.15)))
            axes=node.node('RIG_MATRIX_AXES')
            if axes is None:
                display=node.displayNode();axes=node.createNode('python','RIG_MATRIX_AXES')
                axes.parm('python').set('g=hou.pwd().geometry(); g.clear(); g.createPoints([(0,0,0),(1,0,0),(0,1,0),(0,0,1)])')
                if display:display.setDisplayFlag(True);display.setRenderFlag(True)
        bound=0
        # Bind to the original parent control; hierarchy propagates parent motion.
        for net in car.allSubChildren():
            name=net.userData('b2h_part_object')
            if not name:continue
            parent=records.get(name,{}).get('parent');visited=set()
            while parent in records and parent not in control_nodes and parent not in visited:visited.add(parent);parent=records[parent].get('parent')
            if parent not in control_nodes:continue
            node=control_nodes[parent]
            control_rest=converted_matrix(records[parent]['matrix_world'],data.get('unit_scale',1))
            # Rest is in Geometry-local coordinates, excluding user asset placement.
            geo_rest=converted_matrix(records[car.userData('b2h_asset_parent')]['matrix_world'],data.get('unit_scale',1)) if car.userData('b2h_asset_parent') in records else hou.hmath.identityTransform()
            rest=control_rest*geo_rest.inverted()
            wr=net.node('RIG_PARENT') or net.createNode('attribwrangle','RIG_PARENT')
            wr.setInput(0,net.node('MERGE_MATERIALS'))
            control_source=net.node('CONTROL_MATRIX') or net.createNode('object_merge','CONTROL_MATRIX')
            control_source.parm('objpath1').set(node.node('RIG_MATRIX_AXES').path());control_source.parm('xformtype').set(1)
            wr.setInput(1,control_source)
            code='matrix rest = set('+','.join(repr(v) for v in rest.asTuple())+');\n'
            code+='vector o=point(1,"P",0); vector x=point(1,"P",1)-o; vector y=point(1,"P",2)-o; vector z=point(1,"P",3)-o;\n'
            code+='matrix current=set(x.x,x.y,x.z,0,y.x,y.y,y.z,0,z.x,z.y,z.z,0,o.x,o.y,o.z,1);\n'
            code+='matrix delta = invert(rest) * current;\n@P *= delta;\n'
            code+='if (haspointattrib(0,"N")) @N = normalize(@N * transpose(invert(matrix3(delta))));'
            wr.parm('snippet').set(code);wr.setUserData('b2h_rig_control',node.path());wr.parm('class').set('point')
            normals=net.node('RIG_VERTEX_NORMALS') or net.createNode('attribwrangle','RIG_VERTEX_NORMALS');normals.setInput(0,wr);normals.parm('class').set('vertex')
            normals.setInput(1,control_source)
            normals.parm('snippet').set(code.split('@P *= delta;')[0]+'if(hasvertexattrib(0,"N")) @N=normalize(@N * transpose(invert(matrix3(delta))));')
            net.node('PART_TRANSFORM').setInput(0,normals);net.layoutChildren();bound+=1
        if holder:
            holder.setUserData('b2h_world_holder',asset_name)
            om=holder.node('WORLD_GEOMETRY');om.parm('objpath1').set(car.node('OUT_CAR').path());om.parm('xformtype').set(0)
            bake=holder.node('EXPORT_WORLD_TRANSFORM') or holder.createNode('attribwrangle','EXPORT_WORLD_TRANSFORM');bake.setInput(0,om)
            bake.parm('snippet').set('matrix m=optransform('+json.dumps(car.path())+'); @P *= m; if(haspointattrib(0,"N")) @N=normalize(@N * transpose(invert(matrix3(m))));')
            normals=holder.node('EXPORT_VERTEX_NORMALS') or holder.createNode('attribwrangle','EXPORT_VERTEX_NORMALS');normals.setInput(0,bake);normals.parm('class').set('vertex')
            normals.parm('snippet').set('matrix m=optransform('+json.dumps(car.path())+'); if(hasvertexattrib(0,"N")) @N=normalize(@N * transpose(invert(matrix3(m))));')
            normals.setDisplayFlag(True);normals.setRenderFlag(True)
            imp=next((n for n in hou.node('/stage').children() if n.type().name()=='sopimport' and n.userData('b2h_source')==asset_name),None)
            if imp:imp.parm('soppath').set(normals.path());imp.setUserData('b2h_asset_geometry',car.path())
        repair_paths(mappings)
        controls.layoutChildren();wrapper.layoutChildren();car.setDisplayFlag(True)
        wrapper.setUserData('b2h_controls_bound',str(bound));wrapper.setComment('SAM v012 | '+str(len(names))+' named parts | '+str(bound)+' rigid parent bindings')
        wrapper.setGenericFlag(hou.nodeFlag.DisplayComment,True)
        results.append(wrapper)
    # Retain prior data as a hidden archive for a single-asset project.
    if backend and backend.children() and len([n for n in obj.children() if n.userData('b2h_asset_root')])==1:
        source=results[0].node('SOURCE_DATA') if results else None
        if source:
            old=backend.path();backend.setName('ARCHIVE_PREVIOUS_IMPORTS');renamed=backend.path();backend=hou.moveNodesTo((backend,),source)[0]
            repair_paths([(old,backend.path()),(renamed,backend.path())]);backend.setDisplayFlag(False)
    elif backend and not backend.children():backend.destroy()
    return results
