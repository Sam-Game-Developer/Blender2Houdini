"""Isolated I/O regressions; no running Blender/Houdini scene is changed."""
import ast,importlib.util,json,os,shutil,sys,tempfile,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CONNECTOR=ROOT/'payload/connector'
sys.path.insert(0,str(CONNECTOR))
import texture_paths as paths

def exporter_functions():
    tree=ast.parse((ROOT/'payload/blender2houdini_sam/__init__.py').read_text())
    wanted={'image_export','send_textures_only','send_selected'}
    body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
    scope={'Path':Path,'json':json,'os':os,'shutil':shutil,'_image_cache':{},'exchange_root':paths.exchange_root,'create_transfer':paths.create_transfer,'write_named':paths.write_named}
    exec(compile(ast.Module(body=body,type_ignores=[]),'exporter_functions','exec'),scope)
    return scope

class Image:
    def __init__(self,file='',name='Image',source='FILE',packed=None,fmt='PNG'):
        self.filepath=str(file);self.filepath_raw=str(file);self.library=None;self.name=name;self.source=source;self.packed_file=types.SimpleNamespace(data=packed) if packed is not None else None;self.file_format=fmt;self.colorspace_settings=types.SimpleNamespace(name='sRGB')
    def as_pointer(self):return id(self)
    def save(self):Path(self.filepath_raw).write_bytes(b'generated:'+self.file_format.encode())

class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name).resolve();self.scope=exporter_functions()
        self.scope['bpy']=types.SimpleNamespace(path=types.SimpleNamespace(abspath=lambda p,**kw:p),data=types.SimpleNamespace(filepath=str(self.base/'Sports Car বাংলা.blend')))
        self.project,self.packet,self.meta=paths.create_transfer(self.base/'shot/exchange',self.scope['bpy'].data.filepath,'send')
    def tearDown(self):self.temp.cleanup()
    def image(self,img):return self.scope['image_export'](img,self.project)
    def source(self,name,data=b'original',sub='source'):
        p=self.base/sub/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p
    def fake_hou(self,hip=None):
        hip=hip or self.base/'shot/Shot.hip'
        hou=types.SimpleNamespace(hipFile=types.SimpleNamespace(isNewFile=lambda:False,path=lambda:str(hip)),isUIAvailable=lambda:False)
        sys.modules['hou']=hou
        for name in ['bridge_config','texture_reconnect','project_assets']:sys.modules.pop(name,None)
        return hou
    def test_project_folder_and_legacy_root(self):
        self.assertEqual(self.project,self.base/'shot/Blender2Houdini_Texture/Sports Car বাংলা')
        self.assertEqual(paths.exchange_root(self.project.parent),self.project.parent)
        self.assertEqual(self.packet.parent,self.project/'.b2h')
    def test_unsaved_blender_rejected(self):
        with self.assertRaisesRegex(ValueError,'Save the Blender'):paths.create_transfer(self.base,'','send')
    def test_exact_file_name_bytes_and_source_properties(self):
        src=self.source('Body BaseColor.PNG');img=Image(src,name='Renamed image datablock')
        item=self.image(img);dst=(self.packet/item['path']).resolve()
        self.assertEqual(dst,self.project/src.name);self.assertEqual(dst.read_bytes(),src.read_bytes())
        self.assertEqual(img.filepath,str(src));self.assertEqual(item['source_name'],src.name)
    def test_same_source_updates_same_filename(self):
        src=self.source('Metal.png',b'v1');item=self.image(Image(src));src.write_bytes(b'v2');self.scope['_image_cache'].clear()
        new=self.image(Image(src));self.assertEqual(item['path'],new['path']);self.assertEqual((self.packet/new['path']).read_bytes(),b'v2')
    def test_same_basename_different_sources_do_not_overwrite(self):
        a=self.image(Image(self.source('roughness.png',b'A','one')));b=self.image(Image(self.source('roughness.png',b'B','two')))
        self.assertNotEqual(a['path'],b['path'])
        self.assertEqual(Path(a['path']).name,Path(b['path']).name)
        self.assertEqual((self.packet/a['path']).read_bytes(),b'A');self.assertEqual((self.packet/b['path']).read_bytes(),b'B')
    def test_case_insensitive_collision(self):
        a=self.image(Image(self.source('Metal.PNG',b'A','a')));b=self.image(Image(self.source('metal.png',b'B','b')))
        self.assertIn('duplicates/',b['path']);self.assertEqual((self.packet/a['path']).read_bytes(),b'A')
    def test_unindexed_existing_file_is_preserved(self):
        (self.project/'Albedo.png').write_bytes(b'keep')
        item=self.image(Image(self.source('Albedo.png',b'new')))
        self.assertIn('duplicates/',item['path']);self.assertEqual((self.project/'Albedo.png').read_bytes(),b'keep')
    def test_packed_image_original_bytes_not_png_conversion(self):
        img=Image(self.base/'missing/Glass.jpg',packed=b'packed-jpeg-bytes',fmt='JPEG');item=self.image(img)
        self.assertEqual(Path(item['path']).name,'Glass.jpg');self.assertEqual((self.packet/item['path']).read_bytes(),b'packed-jpeg-bytes')
        self.assertEqual(img.file_format,'JPEG')
    def test_generated_image_preserves_format_and_blender_state(self):
        img=Image(name='Procedural Metal',source='GENERATED',fmt='OPEN_EXR');item=self.image(img)
        self.assertEqual(Path(item['path']).name,'Procedural Metal.exr');self.assertEqual(img.filepath_raw,'');self.assertEqual(img.file_format,'OPEN_EXR')
    def test_missing_image_does_not_publish_file(self):
        with self.assertRaisesRegex(ValueError,'Missing texture'):self.image(Image(self.base/'missing.png'))
        self.assertFalse((self.project/'missing.png').exists())
    def test_texture_only_parent_selection_and_portable_pointer(self):
        material=types.SimpleNamespace(name='Car paint');mesh=types.SimpleNamespace(type='MESH',name='Body',material_slots=[types.SimpleNamespace(material=material)])
        class HashableMesh(types.SimpleNamespace):__hash__=object.__hash__
        mesh=HashableMesh(**mesh.__dict__)
        parent=types.SimpleNamespace(type='EMPTY',children_recursive=[mesh]);scene=types.SimpleNamespace(b2h_exchange=str(self.project.parent))
        context=types.SimpleNamespace(selected_objects=[parent],scene=scene)
        self.scope.update(active_houdini=lambda:None,read_material=lambda m,f,w:{'name':m.name,'maps':{}},watch_houdini_status=lambda *a:None)
        manifest=Path(self.scope['send_textures_only'](context))
        data=json.loads(manifest.read_text());pointer=json.loads((self.project.parent/'latest.json').read_text())
        self.assertEqual(data['project_name'],'Sports Car বাংলা');self.assertEqual(data['objects'],['Body'])
        self.assertEqual(self.project.parent/pointer['relative_manifest'],manifest)
    def test_connector_saved_hip_and_legacy_inbox(self):
        hou=self.fake_hou();import bridge_config
        bridge_config.settings=lambda:{'exchange':str(self.base/'inbox/exchange')}
        self.assertEqual(bridge_config.default_exchange(),self.base/'shot/Blender2Houdini_Texture')
        self.assertEqual(bridge_config.inbox(),self.base/'inbox/Blender2Houdini_Texture')
        self.assertIn(self.base/'shot/exchange',bridge_config.legacy_exchanges())
    def test_localize_new_project_and_legacy_package(self):
        self.fake_hou(self.base/'receiving/Shot.hip');import texture_reconnect
        item=self.image(Image(self.source('Body.png')));data={**self.meta,'materials':{'m':{'name':'Body','maps':{'base_color':item}}}}
        manifest=self.packet/'manifest.json';manifest.write_text(json.dumps(data));(self.packet/'meshes.fbx').write_bytes(b'mesh')
        target=texture_reconnect.local_package(manifest);local=json.loads(target.read_text());tex=local['materials']['m']['maps']['base_color']
        self.assertEqual((target.parent/tex['path']).resolve(),self.base/'receiving/Blender2Houdini_Texture/Sports Car বাংলা/Body.png')
        self.assertEqual((target.parent/'meshes.fbx').read_bytes(),b'mesh');self.assertEqual(texture_reconnect.local_package(manifest),target)
        old=self.base/'old/send_001';(old/'textures').mkdir(parents=True);(old/'manifest.json').write_text('{"materials":{}}');(old/'textures/old.png').write_bytes(b'legacy')
        copied=texture_reconnect.local_package(old/'manifest.json');self.assertEqual((copied.parent/'textures/old.png').read_bytes(),b'legacy')
    def test_save_as_keeps_blender_project_and_original_basename(self):
        hou=self.fake_hou(self.base/'new_shot/NewShot.hip');import project_assets
        item=self.image(Image(self.source('Tyre_N.png')));src=(self.packet/item['path']).resolve()
        class Parm:
            def eval(self):return self.value
            def isLocked(self):return False
            def keyframes(self):return []
            def set(self,v):self.value=v
        parm=Parm();parm.value=str(src)
        owner=types.SimpleNamespace(path=lambda:'/mat/Car',userData=lambda k:'Car' if k=='b2h_source_material' else None,parent=lambda:None)
        node=types.SimpleNamespace(type=lambda:types.SimpleNamespace(name=lambda:'mtlximage'),parm=lambda n:parm,path=lambda:'/mat/Car/image',userData=lambda k:None,parent=lambda:owner)
        hou.node=lambda p:types.SimpleNamespace(allSubChildren=lambda:[node])
        report=project_assets.collect();dest=Path(parm.value)
        self.assertEqual(dest,self.base/'new_shot/Blender2Houdini_Texture/Sports Car বাংলা/Tyre_N.png')
        self.assertEqual(dest.read_bytes(),b'original');self.assertEqual(report['copied'],1)
        # A later send from the same Blender source updates the flat saved-as file.
        self.scope['_image_cache'].clear()
        updated=self.scope['image_export'](Image(self.base/'source/Tyre_N.png'),dest.parent)
        self.assertEqual(updated['path'],'../../Tyre_N.png')

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(LayoutTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'version':'v012','date':'2026-10-20','tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),'scope':'Isolated exporter functions and connector I/O with bpy/hou stubs; real filesystem copies','live_dcc_transfer':'NOT_RUN','render':'NOT_RUN'}
    (ROOT/'TEST_RESULTS.json').write_text(json.dumps(report,indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
