from pathlib import Path
import sys,json,hou,hashlib
from pxr import UsdGeom,UsdShade
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'payload'/'connector'));test=ROOT/'tests'
import houdini_importer,material_builders,houdini_exporter
data=json.loads((test/'fixture.json').read_text());reports=[]
for entry in data['imports']:
    hou.hipFile.clear(suppress_save_prompt=True);hou.hipFile.save(str(test/('fixture_'+entry['builder']+'.hip')))
    node=houdini_importer.import_manifest(Path(entry['manifest']))
    cars=[n for n in hou.node('/obj').children() if n.userData('b2h_live_geometry')];assert len(cars)==2,[(n.path(),n.userData('b2h_live_geometry')) for n in cars]
    car=hou.node('/obj/Sports_Car');assert car and car.type().name()=='geo'
    for path in ['Body','Doors','Wheels','Wheels/Front_Left','Wheels/Front_Right','Wheels/Front_Left/Tyre_FL','MERGE_CAR','OUT_CAR']:assert car.node(path),path
    geometry=car.node('OUT_CAR').geometry();assert not car.node('OUT_CAR').errors(),car.node('OUT_CAR').errors()
    assert set(geometry.primStringAttribValues('name'))==set(data['expected'])-{'Crate'}
    assert geometry.findPrimAttrib('rest_transform') and geometry.findPrimAttrib('rest_pivot') and geometry.findVertexAttrib('uv')
    for name,expected in data['expected'].items():
        container=car if name!='Crate' else hou.node('/obj/Street_Props');g=container.node('OUT_CAR').geometry();prims=[p for p in g.prims() if p.attribValue('name')==name];assert len(prims)==expected['faces']
        actual={tuple(round(v,5) for v in vertex.point().position()*container.worldTransform()) for prim in prims for vertex in prim.vertices()};want={tuple(round(v,5) for v in p) for p in expected['world_points']}
        assert len(actual)==len(want) and all(min(sum((a[i]-b[i])**2 for i in range(3))**.5 for b in want)<2e-5 for a in actual),(entry['builder'],name,actual,want)
        pivot=hou.Vector3(prims[0].attribValue('rest_pivot'))*container.worldTransform();assert all(abs(pivot[i]-expected['world_pivot'][i])<1e-5 for i in range(3)),(name,list(pivot),expected['world_pivot'])
    groups=json.loads(car.userData('b2h_collection_groups'));wheelgroup=geometry.findPrimGroup(groups['Sports_Car/Wheels/Front_Left']);assert {p.attribValue('name') for p in wheelgroup.prims()}=={'Tyre_FL','Rim_FL','BrakeDisc_FL'}
    stage=hou.node('/stage/OUT_FINAL_STAGE').stage();meshes=[p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)];assert len(meshes)==16,len(meshes);assert all(UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0] for p in meshes)
    assert stage.GetPrimAtPath('/cameras/Blender/SceneCamera').IsValid();assert stage.GetPrimAtPath('/lights/Blender/SceneKey').IsValid()
    imports=[n for n in hou.node('/stage').children() if n.type().name()=='sopimport'];assert len(imports)==2
    before=geometry.pointFloatAttribValues('P');material_builders.use_selected('materialx' if entry['builder']=='karma' else 'karma',[car]);assert car.node('OUT_CAR').geometry().pointFloatAttribValues('P')==before
    errors=[(n.path(),list(n.errors())) for n in hou.node('/stage').children() if n.errors()];assert not errors,errors
    reports.append({'builder':entry['builder'],'geometry_containers':2,'nested_collections':True,'part_names':7,'world_positions_units_pivots':'PASS','uvs':True,'front_left_group':True,'usd_meshes':len(meshes),'bound_meshes':len(meshes),'camera_and_light':True,'variant_switch_geometry_unchanged':True,'errors':errors})
    if entry['builder']=='materialx':
        for n in hou.selectedNodes():n.setSelected(False)
        car.setSelected(True);manifest=houdini_exporter.send_selected(test/'return');(test/'return_manifest.txt').write_text(manifest)
        hou.hipFile.save(str(test/'CollectionHierarchy_SAM_v008_Demo.hip'))
(test/'houdini_report.json').write_text(json.dumps(reports,indent=2));print('HOUDINI_COLLECTION_PASS')
