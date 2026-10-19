from pathlib import Path
import sys,json,bpy,math
from mathutils import Vector
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'payload'));test=ROOT/'tests';test.mkdir(exist_ok=True)
import blender2houdini_sam as addon
addon.register();addon.active_houdini=lambda:None;addon.watch_houdini_status=lambda *args:None
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.01
def collection(name,parent):
    col=bpy.data.collections.new(name);parent.children.link(col);return col
car=collection('Sports_Car',scene.collection);body=collection('Body',car);doors=collection('Doors',car);wheels=collection('Wheels',car);fl=collection('Front_Left',wheels);fr=collection('Front_Right',wheels)
props=collection('Street_Props',scene.collection);crates=collection('Crates',props)
parent=bpy.data.objects.new('Car_Root',None);car.objects.link(parent);parent.location=(10,2,1);parent.rotation_euler[2]=.2
mat=bpy.data.materials.new('Paint');mat.use_nodes=True;shader=mat.node_tree.nodes.get('Principled BSDF');image=bpy.data.images.new('Paint_BaseColor',width=4,height=4);image.generated_color=(.8,.1,.03,1);image.filepath_raw=str(test/'Paint_BaseColor.png');image.file_format='PNG';image.save();tex=mat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=image;mat.node_tree.links.new(tex.outputs['Color'],shader.inputs['Base Color'])
metal=bpy.data.materials.new('Metal');metal.use_nodes=True;metal.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=1
objects=[];expected={}
for i,(name,col) in enumerate([('Body',body),('Door_L',doors),('Door_R',doors),('Tyre_FL',fl),('Rim_FL',fl),('BrakeDisc_FL',fl),('Tyre_FR',fr),('Crate',crates)]):
    bpy.ops.mesh.primitive_cube_add(size=2,location=(0,0,0));obj=bpy.context.object;obj.name=name
    for old in list(obj.users_collection):old.objects.unlink(obj)
    col.objects.link(obj);obj.parent=parent if name!='Crate' else None;obj.location=(i*3,0,1);obj.rotation_euler[1]=.17;obj.scale=(1,.8,1.2);obj.data.materials.append(mat);obj.data.materials.append(metal)
    for face in obj.data.polygons:face.material_index=face.index%2
    objects.append(obj)
scene.view_layers[0].update()
for obj in objects:
    coords=[]
    for vertex in obj.data.vertices:
        world=obj.matrix_world@vertex.co;coords.append([world.x*.01,world.z*.01,-world.y*.01])
    origin=obj.matrix_world.translation
    expected[obj.name]={'world_points':coords,'world_pivot':[origin.x*.01,origin.z*.01,-origin.y*.01],'faces':len(obj.data.polygons)}
bpy.ops.object.camera_add(location=(20,-12,10));camera=bpy.context.object;camera.name='SceneCamera';scene.camera=camera
bpy.ops.object.light_add(type='AREA',location=(12,-4,10));bpy.context.object.name='SceneKey';bpy.context.object.data.energy=500
manifest_reports=[]
for mode in ['karma','materialx']:
    scene.b2h_material_builder=mode
    allfile=addon.send_selected(bpy.context,str(test/('full_'+mode)),export_mode='scene',export_objects=objects)
    data=json.loads(Path(allfile).read_text());assert len(data['scene_extras'])==2
    assert {r.get('asset_name') for r in data['objects'] if r['type']=='MESH'}=={'Sports_Car','Street_Props'}
    assert next(r for r in data['objects'] if r['name']=='Tyre_FL')['collection_path']=='Sports_Car/Wheels/Front_Left'
    manifest_reports.append({'builder':mode,'manifest':allfile})
bpy.ops.object.select_all(action='DESELECT');objects[0].select_set(True);bpy.context.view_layer.objects.active=objects[0]
file=addon.send_selected(bpy.context,str(test/'selected_car'))
data=json.loads(Path(file).read_text());assert len({p['source'] for p in data['parts']})==7 and not any(p['source']=='Crate' for p in data['parts'])
bpy.ops.object.select_all(action='DESELECT');objects[-1].select_set(True);bpy.context.view_layer.objects.active=objects[-1];scene.b2h_exchange=str(test/'props');assert bpy.ops.b2h.send_props()=={'FINISHED'}
data=json.loads(Path(json.loads((test/'props'/'latest.json').read_text())['manifest']).read_text());assert {p['source'] for p in data['parts']}=={'Crate'} and data['export_mode']=='props'
(test/'fixture.json').write_text(json.dumps({'imports':manifest_reports,'expected':expected},indent=2));(test/'blender_report.json').write_text(json.dumps({'version':[0,0,8],'full_scene_roots':2,'nested_collection_path':True,'car_expands_complete_root':True,'props_button':True,'camera_and_light_metadata':True},indent=2));print('BLENDER_COLLECTION_PASS')
