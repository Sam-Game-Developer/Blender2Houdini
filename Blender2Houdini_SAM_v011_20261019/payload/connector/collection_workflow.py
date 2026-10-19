"""One OBJ Geometry per asset, nested collection SOP subnets and named parts."""
import hou,json,re,hashlib

def safe(value):
    value=re.sub('[^A-Za-z0-9_]','_',value) or 'part'
    return 'asset_'+value if value[0].isdigit() else value

def group_name(path):return 'collection_'+safe(path)+'_'+hashlib.sha1(path.encode()).hexdigest()[:6]

def converted_matrix(matrix,unit=1):
    f=[[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]];inv=[[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]
    mul=lambda a,b:[[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
    matrix=mul(mul(f,matrix),inv)
    for i in range(3):matrix[i][3]*=unit
    return hou.Matrix4(matrix).transposed()

def create_containers(asset,data,shader_names,bypart):
    obj=hou.node('/obj');records={r['name']:r for r in data.get('objects',[])};groups={}
    for part in data['parts']:
        rec=records.get(part['source'],{});name=rec.get('asset_name',part['source']);groups.setdefault(name,[]).append(part)
    # Re-sends migrate only bridge-owned legacy part containers, preserving edits
    # in the hidden source backend rather than deleting them.
    source_names={p['source'] for p in data['parts']};backend=obj.node('B2H_SOURCE_DATA') or obj.createNode('subnet','B2H_SOURCE_DATA');backend.setDisplayFlag(False)
    for old in list(obj.children()):
        if old.userData('b2h_live_geometry') in source_names and old.userData('b2h_collection_container')!='1':
            world=old.worldTransform();old.destroyUserData('b2h_live_geometry');old.setName('LEGACY_'+old.name(),unique_name=True)
            moved=hou.moveNodesTo((old,),backend)[0];moved.setWorldTransform(world);moved.setDisplayFlag(False)
    top=hou.node('/stage');archive=top.node('B2H_PREVIOUS_IMPORTS') or top.createNode('subnet','B2H_PREVIOUS_IMPORTS')
    for node in list(top.children()):
        if node.type().name()=='sopimport' and node.userData('b2h_simple')=='1' and node.userData('b2h_source') in source_names and node.userData('b2h_source') not in groups:hou.moveNodesTo((node,),archive)
    geometries={};holders=[];outputs={};paths={}
    for asset_name,parts in groups.items():
        car=next((n for n in obj.children() if n.userData('b2h_live_geometry')==asset_name),None) or obj.createNode('geo',safe(asset_name))
        if car.userData('b2h_live_geometry') and car.userData('b2h_collection_container')!='1':raise ValueError('Legacy per-mesh geometry conflicts with '+asset_name+'; import into a new HIP or rename its bridge container first')
        for node in car.children():
            if node.name()!='SOURCE_DATA':node.destroy()
        car.setUserData('b2h_live_geometry',asset_name);car.setUserData('b2h_collection_container','1');car.setUserData('blender_name',asset_name);car.setUserData('b2h_manifest',asset.userData('b2h_manifest'))
        names=list(dict.fromkeys(p['source'] for p in parts));record_list=[records.get(n,{}) for n in names]
        # Collections have no transform: a common source parent supplies the root pivot.
        ancestors=[]
        for name in names:
            chain=[];parent=records.get(name,{}).get('parent')
            while parent in records and parent not in chain:chain.append(parent);parent=records[parent].get('parent')
            ancestors.append(chain)
        common=next((n for n in ancestors[0] if all(n in chain for chain in ancestors)),None) if ancestors else None
        rest_world=converted_matrix(records[common]['matrix_world'],data.get('unit_scale',1)) if common else hou.hmath.identityTransform()
        car.setWorldTransform(rest_world*car.parent().worldTransform() if car.parent()!=obj else rest_world)
        car.setUserData('b2h_object_records',json.dumps(record_list));car.setUserData('b2h_asset_parent',common or '')
        networks={asset_name:car};part_networks={};members={};nodes_by_network={car:[]}
        for name in names:
            rec=records.get(name,{});collection=rec.get('collection_path',asset_name);segments=collection.split('/')
            if segments[0]!=asset_name:segments=[asset_name]+segments
            current=car
            for index in range(1,len(segments)):
                path='/'.join(segments[:index+1])
                if path not in networks:
                    subnet=current.createNode('subnet',safe(segments[index]));subnet.setUserData('b2h_collection_path',path);subnet.setComment(path)
                    networks[path]=subnet;nodes_by_network.setdefault(current,[]).append(subnet);nodes_by_network[subnet]=[]
                current=networks[path]
            partnet=current.createNode('subnet',safe(name));partnet.setUserData('b2h_part_object',name);partnet.setComment(name);nodes_by_network.setdefault(current,[]).append(partnet)
            part_networks[name]=partnet;members[name]=[]
            geometries[name]=car
        for part in parts:
            name=part['source'];rec=records.get(name,{});collection=rec.get('collection_path',asset_name);net=part_networks[name]
            old=hou.node(bypart[part['name']].parm('soppath').eval())
            source=net.createNode('object_merge','SOURCE_'+safe(part['material']));source.parm('objpath1').set(old.path());source.parm('xformtype').set(1)
            world=converted_matrix(rec['matrix_world'],data.get('unit_scale',1)) if rec.get('matrix_world') else hou.hmath.identityTransform();rest=world*car.worldTransform().inverted();pivot=hou.Vector3(0,0,0)*rest
            prim='/World/PROPS/'+'/'.join(safe(s) for s in collection.split('/'))+'/'+safe(name)+'/'+safe(part['material']);paths[part['name']]=prim
            attrs=net.createNode('attribwrangle','ATTR_'+safe(part['material']));attrs.setInput(0,source);attrs.parm('class').set(1)
            values={'name':name,'part_name':name,'asset_name':asset_name,'collection_path':collection,'collection_paths':json.dumps(rec.get('collection_paths',[collection])),'blender_original_name':name,'parent_name':rec.get('parent') or '', 'path':prim,'shop_materialpath':'/stage/MATERIAL_LIBRARY/'+shader_names[part['material']]}
            vex='\n'.join('s@'+key+' = '+json.dumps(value)+';' for key,value in values.items())
            vex+='\ni@blender_order = %d;'%rec.get('order',0)
            vex+='\ni@crash_piece = %d;'%names.index(name)
            vex+='\nv@rest_pivot = set('+','.join(str(v) for v in pivot)+');'
            vex+='\n4@rest_transform = set('+','.join(str(v) for v in rest.asTuple())+');'
            for index in range(1,len(collection.split('/'))+1):vex+='\nsetprimgroup(0,'+json.dumps(group_name('/'.join(collection.split('/')[:index])))+',@primnum,1);'
            vex+='\nsetprimgroup(0,'+json.dumps('part_'+safe(name)+'_'+hashlib.sha1(name.encode()).hexdigest()[:6])+',@primnum,1);'
            attrs.parm('snippet').set(vex)
            out=net.createNode('null','MATERIAL_'+safe(part['material']));out.setInput(0,attrs);out.setUserData('b2h_partname',part['name']);outputs[part['name']]=out.path();members[name].append(out)
            net.setUserData('b2h_rest_transform',json.dumps(list(rest.asTuple())));net.setUserData('b2h_rest_pivot',json.dumps(list(pivot)));net.setUserData('b2h_object_record',json.dumps(rec))
        def finish(network,children,merge_name,out_name,is_root=False):
            merge=network.createNode('merge',merge_name)
            for i,node in enumerate(children):merge.setInput(i,node)
            upstream=merge
            if network.userData('b2h_part_object'):
                transform=network.createNode('xform','PART_TRANSFORM');transform.setInput(0,merge)
                if transform.parmTuple('p'):transform.parmTuple('p').set(json.loads(network.userData('b2h_rest_pivot')))
                upstream=transform
            out=network.createNode('null' if is_root else 'output',out_name);out.setInput(0,upstream);out.setDisplayFlag(True);out.setRenderFlag(True);network.layoutChildren();return out
        for name,network in part_networks.items():finish(network,members[name],'MERGE_MATERIALS','OUT_PART')
        for path,network in sorted(networks.items(),key=lambda x:len(x[0].split('/')),reverse=True):
            if network==car:continue
            finish(network,nodes_by_network[network],'MERGE_COLLECTION','OUT_COLLECTION')
        out=finish(car,nodes_by_network[car],'MERGE_CAR','OUT_CAR',True);car.setDisplayFlag(True)
        car.setUserData('b2h_part_sops',json.dumps({p['name']:outputs[p['name']] for p in parts}));car.setUserData('b2h_collection_groups',json.dumps({path:group_name(path) for path in networks}))
        holder=obj.createNode('geo','B2H_USD_'+safe(asset_name));holder.setDisplayFlag(False);holder.setUserData('b2h_manifest',asset.userData('b2h_manifest'))
        om=holder.createNode('object_merge','WORLD_GEOMETRY');om.parm('objpath1').set(out.path());om.parm('xformtype').set(1);om.setDisplayFlag(True);om.setRenderFlag(True);holders.append((asset_name,holder,om))
    return geometries,holders,outputs,paths
