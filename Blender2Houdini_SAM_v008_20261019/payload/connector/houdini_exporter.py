from bridge_config import default_exchange
"""Static Houdini to Blender PBR exporter, SAM v001."""
import hou,json,uuid,datetime,shutil,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
EXTRA_PBR={'coat':'coat','coat_roughness':'coat_roughness','coat_ior':'coat_IOR','anisotropy':'specular_anisotropy','anisotropy_rotation':'specular_rotation','sheen':'sheen','sheen_roughness':'sheen_roughness','subsurface':'subsurface','subsurface_scale':'subsurface_scale','diffuse_roughness':'diffuse_roughness'}
def read_material(node,folder):
    result={'name':(node.comment() or node.name()) if node else 'Default','base_color':[0.8,0.8,0.8],'roughness':0.5,'metallic':0.0,'maps':{}}
    if not node:return result
    candidates=[node]+list(node.allSubChildren())
    shaders=[n for n in candidates if n.type().name()=='mtlxstandard_surface']
    if len(shaders)!=1:raise ValueError('Use one MaterialX Standard Surface: '+node.path())
    shader=shaders[0];result['base_color']=list(shader.parmTuple('base_color').eval());result['roughness']=shader.parm('specular_roughness').eval();result['metallic']=shader.parm('metalness').eval()
    result.update({'transmission':shader.parm('transmission').eval(),'ior':shader.parm('specular_IOR').eval(),'alpha':shader.parmTuple('opacity').eval()[0],'emission':list(shader.parmTuple('emission_color').eval()),'emission_strength':shader.parm('emission').eval()})
    result['extra_pbr']={key:shader.parm(target).eval() for key,target in EXTRA_PBR.items() if shader.parm(target)}
    links={shader.inputNames()[c.inputIndex()]:c.inputNode() for c in shader.inputConnections()}
    for key,socket in [('base_color','base_color'),('roughness','specular_roughness'),('metallic','metalness'),('normal','normal'),('transmission','transmission'),('alpha','opacity'),('emission','emission_color')]+list(EXTRA_PBR.items()):
        n=links.get(socket)
        if not n:continue
        operations=[]
        while n.userData('b2h_operation'):
            operations.append(json.loads(n.userData('b2h_operation')));n=n.input(0)
        if key=='normal':
            if n.type().name().split('::')[0]!='mtlxnormalmap':raise ValueError('Normal requires MaterialX Normal Map')
            result['normal_strength']=n.parm('scale').eval();n=n.input(0)
        if not n or n.type().name()!='mtlximage':raise ValueError('Bake unsupported MaterialX chain: '+socket)
        src=Path(n.parm('file').eval())
        if not src.is_file():raise ValueError('Missing texture: '+str(src))
        dst=folder/(uuid.uuid4().hex[:10]+src.suffix);shutil.copy2(src,dst)
        result['maps'][key]={'path':'textures/'+dst.name,'colorspace':'sRGB' if key in {'base_color','emission'} and 'srgb' in n.parm('filecolorspace').eval().lower() else 'Non-Color'}
        if operations:result['maps'][key]['operations']=list(reversed(operations))
    return result
def send_selected(exchange=None):
    selected=hou.selectedNodes()
    managed=None
    for n in selected:
        current=hou.node(n.userData('b2h_managed_stage')) if n.userData('b2h_managed_stage') else n
        while current and current.path()!='/':
            if current.userData('b2h_verified')=='1':managed=current;break
            current=current.parent()
        if managed:break
    sources=[]
    assembly_objects={}
    is_assembly=any(n.userData('b2h_global_assembly')=='1' for n in selected)
    if is_assembly:
        for car in hou.node('/obj').children():
            if not car.userData('b2h_live_geometry'):continue
            source_data=json.loads(Path(car.userData('b2h_manifest')).read_text())
            names={p['name']:p for p in source_data['parts']}
            material_nodes=json.loads(car.userData('b2h_material_nodes') or '{}')
            for node in car.allSubChildren():
                part=names.get(node.userData('b2h_partname'))
                if part:sources.append((node,hou.node(material_nodes[part['material']]),part['source']))
            for record in source_data.get('objects',[]):assembly_objects[record['name']]=record
        data={'objects':list(assembly_objects.values()),'unit_scale':1}
    elif managed:
        data=json.loads(Path(managed.userData('b2h_manifest')).read_text(encoding='utf-8'))
        lib=hou.node(managed.userData('b2h_material_library')) if managed.userData('b2h_material_library') else next(n for n in managed.allSubChildren() if n.type().name()=='materiallibrary' and n.name()=='PBR_MATERIALX')
        material_nodes=json.loads(managed.userData('b2h_material_nodes') or '{}')
        part_sops=json.loads(managed.userData('b2h_part_sops') or '{}')
        for part in data['parts']:
            if part['name'] in part_sops:
                sources.append((hou.node(part_sops[part['name']]),hou.node(material_nodes[part['material']]) if part['material'] in material_nodes else lib.node(part['material']),part['source']));continue
            imp=next((n for n in managed.allSubChildren() if n.userData('b2h_partname')==part['name']),managed.node(part['name']))
            sources.append((hou.node(imp.parm('soppath').eval()),lib.node(part['material']),part['source']))
    else:
        collection_cars=[]
        for n in selected:
            current=n
            while current and current.path()!='/':
                if current.userData('b2h_collection_container')=='1':
                    if current not in collection_cars:collection_cars.append(current)
                    break
                current=current.parent()
        if collection_cars:
            assembly_objects={}
            for car in collection_cars:
                source_data=json.loads(Path(car.userData('b2h_manifest')).read_text());part_sops=json.loads(car.userData('b2h_part_sops'));mats=json.loads(car.userData('b2h_material_nodes'))
                parts=[p for p in source_data['parts'] if p['name'] in part_sops]
                for part in parts:sources.append((hou.node(part_sops[part['name']]),hou.node(mats[part['material']]),part['source']))
                records={r['name']:r for r in source_data.get('objects',[])};include={p['source'] for p in parts}
                for name in list(include):
                    parent=records[name].get('parent')
                    while parent in records and parent not in include:include.add(parent);parent=records[parent].get('parent')
                assembly_objects.update({name:records[name] for name in include})
            data={'objects':list(assembly_objects.values()),'unit_scale':1};is_assembly=True
        for n in ([] if collection_cars else selected):
            geo=n if n.type().category()==hou.objNodeTypeCategory() and n.type().name()=='geo' else n.parent() if n.type().category()==hou.sopNodeTypeCategory() else None
            if geo and geo.type().name()=='geo':sources.append((n if n.type().category()==hou.sopNodeTypeCategory() else geo.displayNode(),None,geo.name()))
        if not sources:raise ValueError('Select a Blender2Houdini Stage result, or OBJ geometry/SOP nodes')
    exchange=Path(exchange or default_exchange());exchange.mkdir(parents=True,exist_ok=True)
    package=exchange/('houdini_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    textures=package/'textures';textures.mkdir(parents=True);cache=package/'geometry';cache.mkdir()
    manifest={'schema':'Blender2Houdini-1','author':'SAM','direction':'HoudiniToBlender','fbx':'meshes.fbx','materials':{},'parts':[],'warnings':[]}
    if managed or is_assembly:
        manifest['objects']=data.get('objects',[])
        manifest['unit_scale']=data.get('unit_scale',1)
    temp=hou.node('/obj').createNode('subnet','B2H_EXPORT_TEMP')
    rop=None;material_ids={}
    try:
        for sop,material,source in sources:
            if not sop:raise ValueError('No display geometry: '+source)
            sample=temp.createNode('geo','sample')
            for c in sample.children():c.destroy()
            om=sample.createNode('object_merge');om.parm('objpath1').set(sop.path());om.parm('xformtype').set(1)
            frozen=hou.Geometry();frozen.merge(om.geometry())
            if om.errors() or not frozen.prims():raise ValueError('Empty/error geometry: '+source)
            attr=frozen.findPrimAttrib('shop_materialpath')
            assignments=sorted(set(p.attribValue(attr) for p in frozen.prims())) if attr and not material else ['']
            for assignment in assignments:
                mat=material or (hou.node(assignment) if assignment else None)
                if not mat and sop.parent().parm('shop_materialpath'):mat=hou.node(sop.parent().parm('shop_materialpath').eval())
                matkey=mat.path() if mat else '__default__'
                if matkey not in material_ids:
                    mid='mat_%04d'%len(material_ids);material_ids[matkey]=mid;manifest['materials'][mid]=read_material(mat,textures)
                mid=material_ids[matkey]
                geometry=hou.Geometry();geometry.merge(frozen)
                if attr and not material:geometry.deletePrims([p for p in geometry.prims() if p.attribValue('shop_materialpath')!=assignment],True)
                name='B2H_part%04d'%len(manifest['parts'])
                path=cache/(name+'.bgeo.sc');geometry.saveToFile(str(path))
                geo=temp.createNode('geo',name)
                for c in geo.children():c.destroy()
                file=geo.createNode('file');file.parm('file').set(str(path));file.setDisplayFlag(True);file.setRenderFlag(True)
                manifest['parts'].append({'name':name,'source':source,'material':mid,'faces':len(geometry.prims())})
            sample.destroy()
        rop=hou.node('/out').createNode('filmboxfbx','B2H_EXPORT')
        rop.parm('startnode').set(temp.path());rop.parm('sopoutput').set(str(package/'meshes.fbx'));rop.parm('createsubnetroot').set(False)
        rop.parm('exportkind').set(0)
        rop.parm('convertunits').set(True);rop.parm('axissystem').set('yupright');rop.parm('convertaxis').set(True)
        rop.render(frame_range=(hou.frame(),hou.frame()))
        if rop.errors() or not (package/'meshes.fbx').is_file():raise ValueError(str(rop.errors()))
        (package/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        stage=exchange/'latest_houdini.tmp';stage.write_text(json.dumps({'manifest':str(package/'manifest.json')}),encoding='utf-8');os.replace(stage,exchange/'latest_houdini.json')
        status='SENT TO BLENDER: %d mesh parts, %d PBR materials'%(len(manifest['parts']),len(manifest['materials']))
        if hou.isUIAvailable():hou.ui.setStatusMessage(status)
        print(status);return str(package/'manifest.json')
    finally:
        if rop:rop.destroy()
        temp.destroy()
