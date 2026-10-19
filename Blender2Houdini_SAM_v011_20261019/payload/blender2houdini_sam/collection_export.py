"""Explicit scene collection paths; multiple links have a deterministic primary."""
def collection_index(scene):
    result={};collections=[]
    def walk(collection,path):
        for obj in collection.objects:result.setdefault(obj.name,[]).append(path)
        collections.append({'name':collection.name,'path':'/'.join(path),'parent_path':'/'.join(path[:-1])})
        for child in collection.children:walk(child,path+[child.name])
    for child in scene.collection.children:walk(child,[child.name])
    return result,collections

def object_metadata(scene,objects):
    index,collections=collection_index(scene);result={};warnings=[]
    for obj in objects:
        paths=sorted(index.get(obj.name,[]))
        canonical=paths[0] if paths else [obj.name]
        # A default flat Collection is a scene bucket, not one shared vehicle.
        if canonical[0]=='Collection':canonical=canonical[1:] if len(canonical)>1 else [obj.name]
        result[obj.name]={'collection_path':'/'.join(canonical),'collection_paths':['/'.join(p) for p in paths], 'asset_name':canonical[0], 'asset_collection_path':canonical[0], 'visible_render':not obj.hide_render,'visible_viewport':not obj.hide_viewport}
        if len(paths)>1:warnings.append(obj.name+': multiple collection links; primary '+ '/'.join(canonical)+'; all memberships retained')
    return result,collections,warnings

def expand_assets(scene,selected):
    metadata,_,_=object_metadata(scene,[o for o in scene.objects if o.type=='MESH'])
    roots={metadata[o.name]['asset_name'] for o in selected if o.name in metadata}
    return [o for o in scene.objects if o.type=='MESH' and metadata[o.name]['asset_name'] in roots]

def scene_extras(scene):
    result=[]
    for obj in scene.objects:
        if obj.type not in ('CAMERA','LIGHT'):continue
        item={'name':obj.name,'type':obj.type,'matrix_world':[list(row) for row in obj.matrix_world],'hide_render':obj.hide_render}
        if obj.type=='CAMERA':item.update({'lens':obj.data.lens,'sensor_width':obj.data.sensor_width,'clip_start':obj.data.clip_start,'clip_end':obj.data.clip_end,'projection':obj.data.type,'ortho_scale':obj.data.ortho_scale,'active':scene.camera==obj})
        else:item.update({'light_type':obj.data.type,'energy':obj.data.energy,'color':list(obj.data.color),'size':getattr(obj.data,'size',1),'size_y':getattr(obj.data,'size_y',getattr(obj.data,'size',1)),'spot_size':getattr(obj.data,'spot_size',0.785398)})
        result.append(item)
    return result
