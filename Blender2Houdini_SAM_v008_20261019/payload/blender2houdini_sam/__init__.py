bl_info = {"name": "Blender2Houdini SAM v008", "author": "Samsul Alam Niom", "version": (0, 0, 8), "blender": (4, 0, 0), "location": "3D View > Sidebar > Blender2Houdini", "category": "Import-Export"}
import bpy, bmesh, json, os, shutil, uuid, datetime
from pathlib import Path
from bpy.props import StringProperty, EnumProperty
import bpy.utils.previews
def active_houdini():
    import time
    file=Path(os.getenv('APPDATA',str(Path.home()/'.config')))/'BinaryCGI'/'Blender2Houdini'/'active_houdini.json'
    try:
        data=json.loads(file.read_text(encoding='utf-8-sig'))
        if time.time()-data['updated']<15:return data
    except (OSError,ValueError,KeyError):pass
    return None

def installed_exchange():
    target=active_houdini()
    if target:return target['exchange']
    config=Path(os.getenv('APPDATA',str(Path.home()/'.config')))/'BinaryCGI'/'Blender2Houdini'/'settings.json'
    if config.exists():
        return str(Path(json.loads(config.read_text(encoding='utf-8-sig'))['exchange']))
    return str(Path.home()/'Documents'/'BinaryCGI'/'Blender2Houdini'/'exchange')

class B2H_OT_installed_exchange(bpy.types.Operator):
    bl_idname='b2h.installed_exchange';bl_label='Use Installed Exchange Folder'
    def execute(self,context):
        context.scene.b2h_exchange=installed_exchange()
        context.scene.b2h_status='Exchange folder linked to installed connector'
        return {'FINISHED'}

_previews = None
_image_cache={}
EXTRA_PBR={'coat':('Coat Weight','coat'),'coat_roughness':('Coat Roughness','coat_roughness'),'coat_ior':('Coat IOR','coat_IOR'),'anisotropy':('Anisotropic','specular_anisotropy'),'anisotropy_rotation':('Anisotropic Rotation','specular_rotation'),'sheen':('Sheen Weight','sheen'),'sheen_roughness':('Sheen Roughness','sheen_roughness'),'subsurface':('Subsurface Weight','subsurface'),'subsurface_scale':('Subsurface Scale','subsurface_scale'),'diffuse_roughness':('Diffuse Roughness','diffuse_roughness')}
def image_export(img, folder):
    cache_key=(img.as_pointer(),str(folder))
    if cache_key in _image_cache:return dict(_image_cache[cache_key])
    if img.source in {'TILED', 'MOVIE', 'SEQUENCE'}:
        raise ValueError("MVP supports single image textures; bake UDIM/sequence first: " + img.name)
    src = Path(bpy.path.abspath(img.filepath, library=img.library))
    ext = src.suffix if src.suffix else '.png'
    dst = folder / (uuid.uuid4().hex[:10] + ext)
    if img.packed_file or not src.is_file():
        if img.source != 'GENERATED' and not img.packed_file:
            raise ValueError("Missing texture: " + str(src))
        old, fmt = img.filepath_raw, img.file_format
        try:
            img.filepath_raw = str(dst); img.file_format = 'PNG'; dst = dst.with_suffix('.png'); img.filepath_raw = str(dst); img.save()
        finally:
            img.filepath_raw = old; img.file_format = fmt
    else: shutil.copy2(src, dst)
    result={'path': 'textures/' + dst.name, 'colorspace': img.colorspace_settings.name}
    _image_cache[cache_key]=result
    return dict(result)
def read_material(mat, folder, warnings):
    result = {'name': mat.name if mat else 'Default', 'base_color': [0.8,0.8,0.8], 'roughness': 0.5, 'metallic': 0.0, 'maps': {}}
    if not mat or not mat.use_nodes: return result
    output = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
    bsdf = output.inputs['Surface'].links[0].from_node if output and output.inputs['Surface'].is_linked else None
    if not bsdf or bsdf.type != 'BSDF_PRINCIPLED':
        queue = [bsdf] if bsdf else []; seen = set(); found = []
        while queue:
            node = queue.pop()
            if node in seen: continue
            seen.add(node)
            if node.type == 'BSDF_PRINCIPLED': found.append(node)
            else:
                queue.extend(link.from_node for socket in node.inputs for link in socket.links)
        if len(found) != 1: raise ValueError(mat.name + ': needs one unambiguous Principled PBR shader; bake complex mixtures first')
        bsdf = found[0]; warnings.append(mat.name + ': ray-dependent shader mix omitted; PBR glass/alpha preserved')
    result.update({'transmission':float(bsdf.inputs['Transmission Weight'].default_value),'ior':float(bsdf.inputs['IOR'].default_value),'alpha':float(bsdf.inputs['Alpha'].default_value),'emission':list(bsdf.inputs['Emission Color'].default_value)[:3],'emission_strength':float(bsdf.inputs['Emission Strength'].default_value)})
    result['extra_pbr']={key:float(bsdf.inputs[socket].default_value) for key,(socket,target) in EXTRA_PBR.items() if socket in bsdf.inputs}
    for key, socket in [('base_color','Base Color'),('roughness','Roughness'),('metallic','Metallic'),('normal','Normal'),('transmission','Transmission Weight'),('alpha','Alpha'),('emission','Emission Color')]+[(k,v[0]) for k,v in EXTRA_PBR.items() if v[0] in bsdf.inputs]:
        s = bsdf.inputs[socket]
        if key != 'normal':
            val = s.default_value
            result[key] = list(val)[:3] if key in {'base_color','emission'} else float(val)
        if not s.is_linked: continue
        n = s.links[0].from_node
        operations=[]
        if key=='alpha':
            while n.type in {'CLAMP','RGBTOBW','INVERT'}:
                if n.type=='CLAMP':operations.append({'op':'clamp','min':float(n.inputs['Min'].default_value),'max':float(n.inputs['Max'].default_value)});inp=n.inputs['Value']
                elif n.type=='INVERT':
                    if abs(n.inputs['Fac'].default_value-1)>0.00001:raise ValueError(mat.name+': partial alpha inversion requires baking')
                    operations.append({'op':'invert'});inp=n.inputs['Color']
                else:operations.append({'op':'luminance'});inp=n.inputs['Color']
                if not inp.is_linked:raise ValueError(mat.name+': unsupported alpha chain')
                n=inp.links[0].from_node
        if key == 'normal':
            if n.type != 'NORMAL_MAP' or not n.inputs['Color'].is_linked: raise ValueError(mat.name + ': Normal must use Image Texture > Normal Map')
            if n.space != 'TANGENT': raise ValueError(mat.name + ': only tangent-space normals supported')
            result['normal_strength'] = float(n.inputs['Strength'].default_value)
            n = n.inputs['Color'].links[0].from_node
        if n.type != 'TEX_IMAGE' or not n.image:
            if key in EXTRA_PBR:warnings.append(mat.name+': bake unsupported '+socket+' chain; constant used');continue
            raise ValueError(mat.name + ': bake unsupported ' + socket + ' node chain into an image')
        if n.inputs['Vector'].is_linked:
            v = n.inputs['Vector'].links[0].from_node
            if v.type not in {'UVMAP','TEX_COORD'}: raise ValueError(mat.name + ': bake Mapping/procedural UV transforms first')
            if v.type == 'TEX_COORD' and n.inputs['Vector'].links[0].from_socket.name != 'UV': raise ValueError(mat.name + ': only UV coordinates supported')
        if n.projection != 'FLAT': raise ValueError(mat.name + ': only flat UV image projection supported')
        result['maps'][key] = image_export(n.image, folder)
        if operations:result['maps'][key]['operations']=list(reversed(operations))
    for s in bsdf.inputs:
        if s.is_linked and s.name not in {'Base Color','Roughness','Metallic','Normal','Alpha','Transmission Weight','Emission Color'}|{v[0] for v in EXTRA_PBR.values()}: warnings.append(mat.name + ': ' + s.name + ' is outside MVP scope')
    return result
def send_selected(context, directory, export_mode='car', export_objects=None):
    _image_cache.clear()
    if context.mode != 'OBJECT': raise ValueError("Switch to Object Mode first")
    objects = [o for o in (export_objects if export_objects is not None else context.selected_objects) if o.type == 'MESH']
    from .collection_export import object_metadata,expand_assets,scene_extras
    if export_objects is None:objects=expand_assets(context.scene,objects)
    if not objects: raise ValueError("Select at least one mesh")
    target=active_houdini()
    root = Path(target['exchange'] if target else bpy.path.abspath(directory)); root.mkdir(parents=True, exist_ok=True)
    context.scene.b2h_exchange=str(root)
    package = root / ('send_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    textures = package / 'textures'; textures.mkdir(parents=True)
    data = {'schema': 'Blender2Houdini-1', 'author': 'Samsul Alam Niom', 'fbx': 'meshes.fbx', 'materials': {}, 'parts': [], 'warnings': []}
    data['material_builder']=context.scene.b2h_material_builder
    data['export_mode']=export_mode;data['collection_layout']=1
    metadata,collection_tree,collection_warnings=object_metadata(context.scene,objects)
    data['collections']=collection_tree;data['warnings'].extend(collection_warnings)
    data['scene_extras']=scene_extras(context.scene) if export_mode=='scene' else []
    if export_mode=='scene':data['warnings'].append('Static scene: world/environment shader, render settings, animation, constraints and collection instances are not converted. Native camera/light basics transfer; lighting appearance may differ.')
    if target:data['target_hip']=target['hip']
    ancestry=set(objects)
    for o in objects:
        p=o.parent
        while p:ancestry.add(p);p=p.parent
    ordered=[o for o in context.scene.objects if o in ancestry]
    data['unit_scale']=context.scene.unit_settings.scale_length
    data['objects']=[{'name':o.name,'parent':o.parent.name if o.parent in ancestry else None,'type':o.type,'order':i,'matrix_world':[list(row) for row in o.matrix_world],'collections':[c.name for c in o.users_collection]} for i,o in enumerate(ordered)]
    for record in data['objects']:
        if record['name'] in metadata:record.update(metadata[record['name']])
    if any(o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers) for o in objects):data['warnings'].append('Static evaluated geometry exported; rig controls, skinning and animation are not transferred')
    selected, active = list(context.selected_objects), context.view_layer.objects.active
    temp = []; meshes = []; material_ids = {}
    try:
        for o in objects:
            ev = o.evaluated_get(context.evaluated_depsgraph_get())
            mesh = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=context.evaluated_depsgraph_get())
            meshes.append(mesh)

            for slot in sorted(set(p.material_index for p in mesh.polygons)):
                mat = o.material_slots[slot].material if slot < len(o.material_slots) else None
                mk = mat.name if mat else '__default__'
                if mk not in material_ids:
                    mid = 'mat_%04d' % len(material_ids); material_ids[mk] = mid
                    data['materials'][mid] = read_material(mat, textures, data['warnings'])
                mid = material_ids[mk]
                if data['materials'][mid]['maps'] and not mesh.uv_layers: raise ValueError(o.name + ': UV map required for image textures')
                partmesh = mesh.copy(); meshes.append(partmesh)
                bm = bmesh.new(); bm.from_mesh(partmesh)
                bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != slot], context='FACES')
                bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
                bm.to_mesh(partmesh); bm.free()
                name = 'B2H_' + package.name.rsplit('_',1)[-1] + '_part%04d' % len(temp)
                part = bpy.data.objects.new(name, partmesh); context.scene.collection.objects.link(part)
                part.matrix_world = o.matrix_world.copy()
                partmesh.materials.clear()
                temp.append(part)
                data['parts'].append({'name': part.name, 'source': o.name, 'source_parent':o.parent.name if o.parent else None,'source_matrix_world':[list(row) for row in o.matrix_world],'material': mid, 'faces': len(partmesh.polygons)})
        for o in selected: o.select_set(False)
        for o in temp: o.select_set(True)
        context.view_layer.objects.active = temp[0]
        bpy.ops.export_scene.fbx(filepath=str(package / 'meshes.fbx'), use_selection=True, object_types={'MESH'}, bake_anim=False, axis_forward='-Z', axis_up='Y', path_mode='COPY', apply_unit_scale=True, use_mesh_modifiers=False)
        (package / 'manifest.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
        pointer = root / 'latest.json'; stage = root / 'latest.tmp'
        stage.write_text(json.dumps({'manifest': str(package / 'manifest.json')}), encoding='utf-8'); os.replace(stage, pointer)
        context.scene.b2h_status = 'SENT: %d mesh parts, %d materials%s' % (len(temp), len(material_ids), ('; %d warnings' % len(data['warnings'])) if data['warnings'] else '')
        watch_houdini_status(context.scene,root,package/'manifest.json')
        return str(package / 'manifest.json')
    finally:
        for o in temp: bpy.data.objects.remove(o, do_unlink=True)
        for m in meshes:
            if m.users == 0: bpy.data.meshes.remove(m)
        for o in selected: o.select_set(True)
        context.view_layer.objects.active = active
class B2H_OT_send(bpy.types.Operator):
    bl_idname = 'b2h.send'; bl_label = 'Send Car / Object'; bl_description = 'Send complete asset root collections containing the selected meshes'
    def execute(self, context):
        try:
            send_selected(context, context.scene.b2h_exchange)
            self.report({'INFO'}, context.scene.b2h_status); return {'FINISHED'}
        except Exception as e:
            context.scene.b2h_status = 'ERROR: ' + str(e); self.report({'ERROR'}, str(e)); return {'CANCELLED'}
class B2H_OT_send_scene(bpy.types.Operator):
    bl_idname='b2h.send_scene';bl_label='Send Full Scene + Collections'
    def execute(self,context):
        selected=list(context.selected_objects);active=context.view_layer.objects.active
        try:
            for o in selected:o.select_set(False)
            send_selected(context,context.scene.b2h_exchange,export_mode='scene',export_objects=[o for o in context.scene.objects if o.type=='MESH'])
            self.report({'INFO'},context.scene.b2h_status);return {'FINISHED'}
        except Exception as e:context.scene.b2h_status='ERROR: '+str(e);self.report({'ERROR'},str(e));return {'CANCELLED'}
        finally:
            for o in context.selected_objects:o.select_set(False)
            for o in selected:o.select_set(True)
            context.view_layer.objects.active=active
class B2H_OT_send_props(bpy.types.Operator):
    bl_idname='b2h.send_props';bl_label='Send Props';bl_description='Send selected prop root collections as individual Geometry containers'
    def execute(self,context):
        try:send_selected(context,context.scene.b2h_exchange,export_mode='props');return {'FINISHED'}
        except Exception as error:context.scene.b2h_status='ERROR: '+str(error);return {'CANCELLED'}

def receive_houdini(context):
    root = Path(bpy.path.abspath(context.scene.b2h_exchange))
    manifest = Path(json.loads((root/'latest_houdini.json').read_text(encoding='utf-8'))['manifest'])
    if not manifest.exists(): manifest = root/manifest.parent.name/'manifest.json'
    data = json.loads(manifest.read_text(encoding='utf-8')); package = manifest.parent
    before=set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(package/data['fbx']), use_anim=False, use_image_search=False)
    new=[o for o in bpy.data.objects if o not in before]
    mats={}
    for mid,entry in data['materials'].items():
        mat=bpy.data.materials.new(entry['name']+'_FromHoudini');mat.use_nodes=True
        shader=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        shader.inputs['Base Color'].default_value=(*entry['base_color'],1)
        shader.inputs['Roughness'].default_value=entry['roughness'];shader.inputs['Metallic'].default_value=entry['metallic']
        shader.inputs['Transmission Weight'].default_value=entry.get('transmission',0);shader.inputs['IOR'].default_value=entry.get('ior',1.5);shader.inputs['Alpha'].default_value=entry.get('alpha',1)
        shader.inputs['Emission Color'].default_value=(*entry.get('emission',[0,0,0]),1);shader.inputs['Emission Strength'].default_value=entry.get('emission_strength',0)
        for key,val in entry.get('extra_pbr',{}).items():
            if key in EXTRA_PBR and EXTRA_PBR[key][0] in shader.inputs:shader.inputs[EXTRA_PBR[key][0]].default_value=val
        for key,texture in entry['maps'].items():
            img=bpy.data.images.load(str(package/texture['path']),check_existing=False)
            img.colorspace_settings.name='sRGB' if key in {'base_color','emission'} and texture['colorspace']=='sRGB' else 'Non-Color'
            image=mat.node_tree.nodes.new('ShaderNodeTexImage');image.image=img
            if key=='normal':
                normal=mat.node_tree.nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=entry.get('normal_strength',1)
                mat.node_tree.links.new(image.outputs['Color'],normal.inputs['Color']);mat.node_tree.links.new(normal.outputs['Normal'],shader.inputs['Normal'])
            else:
                value=image.outputs['Color']
                for op in texture.get('operations',[]):
                    if op['op']=='invert':n=mat.node_tree.nodes.new('ShaderNodeInvert');mat.node_tree.links.new(value,n.inputs['Color']);value=n.outputs['Color']
                    elif op['op']=='luminance':n=mat.node_tree.nodes.new('ShaderNodeRGBToBW');mat.node_tree.links.new(value,n.inputs['Color']);value=n.outputs['Val']
                    elif op['op']=='clamp':n=mat.node_tree.nodes.new('ShaderNodeClamp');n.inputs['Min'].default_value=op['min'];n.inputs['Max'].default_value=op['max'];mat.node_tree.links.new(value,n.inputs['Value']);value=n.outputs['Result']
                target=EXTRA_PBR[key][0] if key in EXTRA_PBR else {'base_color':'Base Color','roughness':'Roughness','metallic':'Metallic','alpha':'Alpha','transmission':'Transmission Weight','emission':'Emission Color'}[key]
                mat.node_tree.links.new(value,shader.inputs[target])
        mats[mid]=mat
    collection=bpy.data.collections.new('From_Houdini_'+package.name);context.scene.collection.children.link(collection)
    for entry in data['parts']:
        matches=[o for o in new if o.type=='MESH' and (o.name==entry['name'] or o.name.startswith(entry['name']+'.'))]
        if len(matches)!=1:raise ValueError('Returned FBX part not found uniquely: '+entry['name'])
        obj=matches[0];obj.data.materials.clear();obj.data.materials.append(mats[entry['material']])
        obj['b2h_source']=entry['source']
    for obj in new:
        for c in list(obj.users_collection):c.objects.unlink(obj)
        collection.objects.link(obj)
    # Reassemble material pieces into the original logical mesh objects.
    from mathutils import Matrix
    grouped={}
    for obj in new:
        if obj.type=='MESH':grouped.setdefault(obj.get('b2h_source',obj.name),[]).append(obj)
    rebuilt={}
    for source,pieces in grouped.items():
        bpy.ops.object.select_all(action='DESELECT')
        for obj in pieces:obj.select_set(True)
        context.view_layer.objects.active=pieces[0]
        if len(pieces)>1:bpy.ops.object.join()
        obj=context.view_layer.objects.active
        obj.name=source;obj['b2h_original_name']=source;rebuilt[source]=obj
    records=sorted(data.get('objects',[]),key=lambda r:r['order'])
    for rec in records:
        if rec['name'] not in rebuilt:
            obj=bpy.data.objects.new(rec['name'],None);collection.objects.link(obj);rebuilt[rec['name']]=obj
        obj=rebuilt[rec['name']];obj['b2h_order']=rec['order'];obj['b2h_original_name']=rec['name']
        if rec.get('matrix_world'):
            matrix=Matrix(rec['matrix_world'])
            if obj.type=='MESH':obj.data.transform(matrix.inverted() @ obj.matrix_world)
            obj.matrix_world=matrix
    for rec in records:
        obj=rebuilt[rec['name']];world=obj.matrix_world.copy()
        obj.parent=rebuilt.get(rec.get('parent'));obj.matrix_world=world
        context.view_layer.update()
    for rec in records:
        obj=rebuilt[rec['name']]
        if obj.name in collection.objects:collection.objects.unlink(obj)
        collection.objects.link(obj)
    restored_collections={}
    for rec in records:
        path=rec.get('collection_path')
        if not path:continue
        parent_collection=collection
        segments=path.split('/')
        for index,segment in enumerate(segments):
            key='/'.join(segments[:index+1])
            if key not in restored_collections:
                child=bpy.data.collections.new(segment);parent_collection.children.link(child);restored_collections[key]=child
            parent_collection=restored_collections[key]
        obj=rebuilt[rec['name']]
        if obj.name in collection.objects:collection.objects.unlink(obj)
        parent_collection.objects.link(obj)
    new=[rebuilt[r['name']] for r in records] if records else list(rebuilt.values())
    context.scene.b2h_status='RECEIVED: %d mesh parts, %d PBR materials'%(len(data['parts']),len(mats))
    return new
class B2H_OT_receive(bpy.types.Operator):
    bl_idname='b2h.receive';bl_label='Receive from Houdini'
    def execute(self,context):
        try:receive_houdini(context);self.report({'INFO'},context.scene.b2h_status);return {'FINISHED'}
        except Exception as e:context.scene.b2h_status='ERROR: '+str(e);self.report({'ERROR'},str(e));return {'CANCELLED'}
def send_textures_only(context, directory=None, all_scene=False):
    _image_cache.clear();target=active_houdini()
    root=Path(target['exchange'] if target else bpy.path.abspath(directory or context.scene.b2h_exchange));root.mkdir(parents=True,exist_ok=True)
    objects=[o for o in (context.scene.objects if all_scene else context.selected_objects) if o.type=='MESH']
    if not objects:raise ValueError('Select mesh objects, or enable All Scene Textures')
    package=root/('textures_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);textures=package/'textures';textures.mkdir(parents=True)
    data={'schema':'Blender2Houdini-1','kind':'textures_only','author':'Samsul Alam Niom','materials':{},'warnings':[],'objects':[o.name for o in objects]}
    if target:data['target_hip']=target['hip']
    names={}
    for obj in objects:
        for slot in obj.material_slots:
            mat=slot.material
            if mat and mat.name not in names:names[mat.name]=mat
    for mat in names.values():data['materials']['mat_%04d'%len(data['materials'])]=read_material(mat,textures,data['warnings'])
    if not data['materials']:raise ValueError('No materials on the chosen meshes')
    manifest=package/'manifest.json';manifest.write_text(json.dumps(data,indent=2),encoding='utf-8')
    temp=root/'latest.tmp';temp.write_text(json.dumps({'manifest':str(manifest)}),encoding='utf-8');os.replace(temp,root/'latest.json')
    context.scene.b2h_exchange=str(root);context.scene.b2h_status='SENT TEXTURES ONLY: %d materials; geometry unchanged'%len(data['materials'])
    watch_houdini_status(context.scene,root,manifest);return str(manifest)

class B2H_OT_textures_only(bpy.types.Operator):
    bl_idname='b2h.send_textures_only';bl_label='Send Textures Only'
    def execute(self,context):
        try:send_textures_only(context,all_scene=context.scene.b2h_all_scene_textures);return {'FINISHED'}
        except Exception as error:context.scene.b2h_status='ERROR: '+str(error);return {'CANCELLED'}

class B2H_PT_panel(bpy.types.Panel):
    bl_label = 'Blender2Houdini SAM v008'; bl_idname = 'B2H_PT_panel'; bl_space_type = 'VIEW_3D'; bl_region_type = 'UI'; bl_category = 'Blender2Houdini'
    def draw(self, context):
        layout = self.layout
        layout.label(text='Samsul Alam Niom | 2026-10-19')
        layout.prop(context.scene, 'b2h_exchange', text='Exchange folder')
        layout.operator('b2h.installed_exchange',icon='FILE_REFRESH')
        layout.prop(context.scene, 'b2h_material_builder', text='Houdini materials')
        layout.operator('b2h.send', icon_value=_previews['houdini'].icon_id if _previews and 'houdini' in _previews else 0)
        layout.operator('b2h.send_scene', icon_value=_previews['houdini'].icon_id if _previews and 'houdini' in _previews else 0)
        layout.operator('b2h.send_props',icon='OUTLINER_OB_MESH')
        layout.operator('b2h.receive', icon_value=_previews['houdini'].icon_id if _previews and 'houdini' in _previews else 0)
        layout.prop(context.scene,'b2h_all_scene_textures',text='All Scene Textures')
        layout.operator('b2h.send_textures_only',icon='TEXTURE')
        layout.label(text=context.scene.b2h_status)
        layout.label(text='Automatic Send | Send back + Receive')
def register():
    global _previews
    for c in (B2H_OT_installed_exchange, B2H_OT_send, B2H_OT_send_scene, B2H_OT_send_props, B2H_OT_receive, B2H_OT_textures_only, B2H_PT_panel): bpy.utils.register_class(c)
    bpy.types.Scene.b2h_all_scene_textures=bpy.props.BoolProperty(name='All Scene Textures',default=False)
    bpy.types.Scene.b2h_exchange = StringProperty(name='Exchange', subtype='DIR_PATH', default=installed_exchange())
    bpy.types.Scene.b2h_material_builder = EnumProperty(name='Houdini materials', items=[('karma','Karma Material Builder','Recommended for local Karma XPU rendering'),('materialx','USD MaterialX Builder','Standard MaterialX for portability')], default='karma')
    bpy.types.Scene.b2h_status = StringProperty(name='Status', default='Ready: select meshes')
    _previews = bpy.utils.previews.new()
    icon = Path(__file__).resolve().parent / 'icons' / 'houdini.png'
    if icon.exists(): _previews.load('houdini', str(icon), 'IMAGE')
def unregister():
    global _previews
    if _previews: bpy.utils.previews.remove(_previews); _previews = None
    for c in (B2H_PT_panel, B2H_OT_textures_only, B2H_OT_receive, B2H_OT_send_props, B2H_OT_send_scene, B2H_OT_send, B2H_OT_installed_exchange): bpy.utils.unregister_class(c)
    del bpy.types.Scene.b2h_all_scene_textures
    del bpy.types.Scene.b2h_material_builder
    del bpy.types.Scene.b2h_exchange; del bpy.types.Scene.b2h_status
if __name__ == '__main__': register()


def watch_houdini_status(scene,folder,manifest):
    import time
    deadline=time.monotonic()+300
    source_name=scene.name
    def poll():
        try:
            target=bpy.data.scenes.get(source_name)
            if not target or time.monotonic()>deadline:return None
            file=Path(folder)/'houdini_status.json'
            if file.exists():
                status=json.loads(file.read_text())
                if any(Path(status.get(key,'')).resolve()==Path(manifest).resolve() for key in ['manifest','source_manifest']):
                    target.b2h_status=('HOUDINI: ' if status['ok'] else 'HOUDINI ERROR: ')+status['message']
                    for area in bpy.context.screen.areas:area.tag_redraw()
                    return None
            return 0.75
        except Exception:return None
    bpy.app.timers.register(poll,first_interval=1)
