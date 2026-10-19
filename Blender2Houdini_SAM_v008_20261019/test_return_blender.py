from pathlib import Path
import sys,json,bpy
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'payload'));test=ROOT/'tests'
import blender2houdini_sam as addon
addon.register();addon.active_houdini=lambda:None
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.context.scene.b2h_exchange=str(test/'return')
objects=addon.receive_houdini(bpy.context);meshes=[o for o in objects if o.type=='MESH'];assert len(meshes)==7
assert all(o.data.uv_layers for o in meshes)
tyre=next(o for o in meshes if o.get('b2h_original_name')=='Tyre_FL');assert any(c.name.startswith('Front_Left') for c in tyre.users_collection)
assert tyre.parent and tyre.parent.get('b2h_original_name')=='Car_Root'
expected=json.loads((test/'fixture.json').read_text())['expected'];unit=.01
for obj in meshes:
    name=obj.get('b2h_original_name');coords=[obj.matrix_world@v.co for v in obj.data.vertices]
    actual={(round(v.x,5),round(v.z,5),round(-v.y,5)) for v in coords};want={tuple(round(v,5) for v in p) for p in expected[name]['world_points']}
    assert len(actual)==len(want) and all(min(sum((a[i]-b[i])**2 for i in range(3))**.5 for b in want)<2e-5 for a in actual),(name,actual,want)
(test/'return_report.json').write_text(json.dumps({'meshes':7,'uvs':True,'collections_restored':True,'parent_preserved':True,'world_positions':'PASS'},indent=2));print('RETURN_COLLECTION_PASS')
