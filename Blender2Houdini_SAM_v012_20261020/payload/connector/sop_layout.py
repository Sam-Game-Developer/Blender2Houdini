"""One visible OBJ Geometry per asset; parent groups become SOP Transform branches."""
import hou,json,hashlib
from pathlib import Path
from collection_workflow import safe,converted_matrix

def capture(data):
    saved={}
    for geo in hou.node('/obj').children():
        if geo.userData('b2h_sop_asset')!='1':continue
        transforms={}
        for n in geo.allSubChildren():
            if n.type().name()!='xform' or not n.userData('b2h_transform_source'):continue
            transforms[n.userData('b2h_transform_source')]={p.name():(p.keyframes() or p.eval()) for p in n.parms() if p.name() in ['tx','ty','tz','rx','ry','rz','sx','sy','sz','scale']}
        saved[geo.userData('b2h_live_geometry')]={'transforms':transforms,'pre':geo.preTransform(),'parms':{p.name():(p.keyframes() or p.eval()) for p in geo.parms() if p.name() in ['tx','ty','tz','rx','ry','rz','sx','sy','sz','px','py','pz','prx','pry','prz']}}
    return saved

def _restore(node,values):
    for name,value in values.items():
        p=node.parm(name)
        if p is None:continue
        if isinstance(value,tuple) and value and isinstance(value[0],hou.BaseKeyframe):p.setKeyframes(value)
        else:p.set(value)

def apply(data,saved=None):
    saved=saved or {};obj=hou.node('/obj');records={r['name']:r for r in data.get('objects',[])}
    for geo in list(obj.children()):
        if geo.type().name()!='geo' or geo.userData('b2h_collection_container')!='1':continue
        asset_name=geo.userData('b2h_live_geometry')
        parts=[p for p in data['parts'] if records.get(p['source'],{}).get('asset_name',p['source'])==asset_name]
        if not parts:continue
        manifest=Path(geo.userData('b2h_manifest'));cache=manifest.parent/'sop_geometry';cache.mkdir(exist_ok=True)
        old_outputs=json.loads(geo.userData('b2h_part_sops'));materials=json.loads(geo.userData('b2h_material_nodes'))
        rest_world=geo.worldTransform();inverse=rest_world.inverted();names=list(dict.fromkeys(p['source'] for p in parts))
        common=geo.userData('b2h_asset_parent');parents=set()
        def chain(name):
            values=[];visited=set()
            while name in records and name not in visited:visited.add(name);values.append(name);name=records[name].get('parent')
            return list(reversed(values))
        for name in names:parents.update(n for n in chain(name)[:-1] if records[n].get('type')=='EMPTY' and n!=common)
        new_paths={};cached={};old_paths={}
        for part in parts:
            sop=hou.node(old_outputs[part['name']]);g=hou.Geometry();g.merge(sop.geometry())
            if not g.prims() or sop.errors():raise ValueError('Empty source part: '+part['source'])
            old_paths[part['name']]=set(g.primStringAttribValues('path'))
            segments=[asset_name]+chain(part['source'])+[part['material']]
            path='/World/PROPS/'+'/'.join(safe(s) for s in segments);new_paths[part['name']]=path
            identity=g.findPrimAttrib('b2h_part_id') or g.addAttrib(hou.attribType.Prim,'b2h_part_id','')
            for prim in g.prims():prim.setAttribValue('path',path);prim.setAttribValue(identity,part['name'])
            dest=cache/(safe(part['name'])+'.bgeo.sc');g.saveToFile(str(dest));cached[part['name']]=dest
        # Existing source archives are preserved, while all editable geometry is SOP-based.
        for node in list(geo.children()):
            if node.name()!='SOURCE_DATA':node.destroy()
        source=geo.node('SOURCE_DATA') or geo.createNode('objnet','SOURCE_DATA')
        source.setComment('Internal imported sources and world-space Solaris output')
        mappings=[]
        legacy=next((n for n in obj.children() if n.userData('b2h_asset_root')==asset_name),None)
        if legacy:
            old=legacy.path();legacy.setName('PREVIOUS_OBJ_HIERARCHY',unique_name=True);renamed=legacy.path();moved=hou.moveNodesTo((legacy,),source)[0];moved.setDisplayFlag(False)
            mappings.extend([(old,moved.path()),(renamed,moved.path())])
        backend=obj.node('B2H_SOURCE_DATA')
        if backend and len([n for n in obj.children() if n.userData('b2h_live_geometry')])==1:
            old=backend.path();moved=hou.moveNodesTo((backend,),source)[0];moved.setDisplayFlag(False);mappings.append((old,moved.path()))
        from asset_workflow import repair_paths
        repair_paths(mappings)
        if geo.name()!=safe(asset_name) and obj.node(safe(asset_name)) is None:geo.setName(safe(asset_name))
        nets={common:geo};children={geo:[]};part_nets={}
        for name in sorted(parents,key=lambda name:(len(chain(name)),records[name].get('order',0))):
            parent=records[name].get('parent');owner=nets.get(parent,geo)
            net=owner.createNode('subnet',safe(name));net.setUserData('b2h_parent_group',name);net.setComment(name)
            nets[name]=net;children.setdefault(owner,[]).append(net);children[net]=[]
        def pivot(name):
            matrix=converted_matrix(records[name]['matrix_world'],data.get('unit_scale',1))*inverse if name in records else hou.hmath.identityTransform()
            return matrix.extractTranslates(),matrix.extractRotates()
        def finish(net,items,source_name,is_root=False):
            merge=net.createNode('merge','MERGE_CAR' if is_root else 'MERGE_PARTS')
            for i,n in enumerate(items):merge.setInput(i,n)
            label=(safe(common) if common else 'Car_Main') if is_root else 'TRANSFORM_'+safe(source_name)
            transform=net.createNode('xform',label);transform.setInput(0,merge);transform.setUserData('b2h_transform_source',source_name or '__ASSET__')
            p,r=pivot(source_name)
            transform.parmTuple('p').set(p)
            if transform.parmTuple('pr'):transform.parmTuple('pr').set(r)
            _restore(transform,saved.get(asset_name,{}).get('transforms',{}).get(source_name or '__ASSET__',{}))
            out=net.createNode('null' if is_root else 'output','OUT_CAR' if is_root else 'OUT_GROUP');out.setInput(0,transform);out.setDisplayFlag(True);out.setRenderFlag(True);net.layoutChildren();return out
        by_name={name:[] for name in names}
        for name in names:
            owner=nets.get(records.get(name,{}).get('parent'),geo);net=owner.createNode('subnet',safe(name));net.setUserData('b2h_part_object',name);part_nets[name]=net;children.setdefault(owner,[]).append(net)
        for part in parts:
            net=part_nets[part['source']];file=net.createNode('file','SOURCE_'+safe(part['material']));file.parm('file').set(cached[part['name']].as_posix())
            material=net.createNode('attribwrangle','MATERIAL_'+safe(part['material']));material.setInput(0,file);material.parm('class').set('primitive');material.parm('snippet').set('s@shop_materialpath='+json.dumps(materials[part['material']])+';')
            by_name[part['source']].append(material)
        for name,net in part_nets.items():finish(net,by_name[name],name)
        for name in sorted(parents,key=lambda name:len(chain(name)),reverse=True):finish(nets[name],children[nets[name]],name)
        out=finish(geo,children[geo],common,True)
        previous=saved.get(asset_name)
        if previous:geo.setPreTransform(previous['pre']);_restore(geo,previous['parms'])
        world=source.node('WORLD_EXPORT') or source.createNode('geo','WORLD_EXPORT')
        for n in world.children():n.destroy()
        om=world.createNode('object_merge','ASSET_WORLD_GEOMETRY');om.parm('objpath1').set(out.path());om.parm('xformtype').set(1)
        stage_out=world.createNode('null','OUT_STAGE');stage_out.setInput(0,om);stage_out.setDisplayFlag(True);stage_out.setRenderFlag(True);world.setDisplayFlag(False)
        part_outputs={}
        for part in parts:
            split=world.createNode('blast','EXPORT_'+safe(part['name']));split.setInput(0,stage_out);split.parm('group').set('@b2h_part_id='+part['name']);split.parm('negate').set(1);split.setUserData('b2h_partname',part['name']);part_outputs[part['name']]=split.path()
        world.layoutChildren()
        imp=next(n for n in hou.node('/stage').children() if n.type().name()=='sopimport' and n.userData('b2h_source')==asset_name)
        imp.parm('soppath').set(stage_out.path());imp.setUserData('b2h_asset_geometry',geo.path())
        assign=hou.node('/stage/ASSIGN_MATERIALS')
        replacements={path:new_paths[name] for name,paths in old_paths.items() for path in paths}
        for i in range(1,assign.parm('nummaterials').eval()+1):
            parm=assign.parm('primpattern%d'%i);pattern=parm.eval()
            parm.set(' '.join(replacements.get(token[:-3],token[:-3])+'/**' if token.endswith('/**') else replacements.get(token,token) for token in pattern.split()))
        geo.setUserData('b2h_part_sops',json.dumps(part_outputs));geo.setUserData('b2h_sop_asset','1');geo.setUserData('b2h_layout','single_geometry');geo.setUserData('b2h_parent_layout','sop')
        geo.setComment('SAM v012 | One Geometry | '+str(len(names))+' named parts | editable SOP transforms');geo.setGenericFlag(hou.nodeFlag.DisplayComment,True)
        for n in hou.node('/stage').allSubChildren():
            if n.userData('b2h_verified')=='1' and n.userData('b2h_manifest')==str(manifest):n.setUserData('b2h_part_sops',json.dumps(part_outputs))
        source.setPosition(hou.Vector2(-8,-3));geo.setDisplayFlag(True)
