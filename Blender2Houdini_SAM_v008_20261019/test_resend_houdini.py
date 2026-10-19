from pathlib import Path
import sys,json,hou,shutil
from pxr import UsdGeom
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'payload/connector'));test=ROOT/'tests'
import houdini_importer
entry=json.loads((test/'fixture.json').read_text())['imports'][0];manifest=Path(entry['manifest'])
hou.hipFile.save(str(test/'resend.hip'));houdini_importer.import_manifest(manifest)
copy=test/'resend_package';shutil.copytree(manifest.parent,copy,dirs_exist_ok=True);data=json.loads((copy/'manifest.json').read_text());data['materials']['mat_0000']['roughness']=.73;(copy/'manifest.json').write_text(json.dumps(data))
houdini_importer.import_manifest(copy/'manifest.json')
cars=[n for n in hou.node('/obj').children() if n.userData('b2h_live_geometry')];assert len(cars)==2
assert hou.node('/stage/ASSIGN_MATERIALS').parm('nummaterials').eval()==16
assert sum(p.IsA(UsdGeom.Mesh) for p in hou.node('/stage/OUT_FINAL_STAGE').stage().Traverse())==16
assert all(not n.errors() for n in hou.node('/stage').children())
(test/'resend_report.json').write_text(json.dumps({'asset_containers_after_resend':2,'bindings_after_resend':16,'meshes_after_resend':16,'no_duplicate_geometry_or_bindings':True},indent=2));print('RESEND_PASS')
