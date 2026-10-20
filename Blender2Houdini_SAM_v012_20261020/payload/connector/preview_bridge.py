"""Automatic OBJ previews, rig hierarchy and Blender-style Karma lighting."""
import hou,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def safe(name):return re.sub(r'[^A-Za-z0-9_]', '_',name)
def apply_color():
    config=ROOT/'resources'/'blender_ocio'/'config.ocio'
    if config.exists() and Path(hou.Color.ocio_configPath()).resolve()!=config.resolve():
        hou.putenv('OCIO',str(config));hou.Color.reloadOCIO()
    if hou.isUIAvailable():
        for p in hou.ui.paneTabs():
            if isinstance(p,hou.SceneViewer):
                p.setUsingOCIO(True);p.setOCIODisplayView('sRGB','AgX')
def upgrade(stage):
    from houdini_importer import portable
    apply_color()
    if stage.userData('b2h_preview_fixed')=='1':return
    lib=next(n for n in stage.allSubChildren() if n.type().name()=='materiallibrary')
    for n in lib.allSubChildren():
        if n.type().name()=='mtlximage' and n.parm('filecolorspace').eval()=='srgb_texture':n.parm('filecolorspace').set('sRGB')
    dome=stage.createNode('domelight','BLENDER_STUDIO_HDRI')
    dome.setInput(0,stage.node('OUT_KARMA'))
    dome.parm('xn__inputstexturefile_control_shbh').set('set')
    dome.parm('xn__inputstexturefile_r3ah').set(portable(ROOT/'resources'/'forest.exr'))
    stage.setUserData('b2h_preview_node',dome.path());stage.setUserData('b2h_preview_fixed','1')

def focus(stage):
    hou.putenv('KARMA_XPU_DISABLE_EMBREE_DEVICE','1')
    hou.unsetenv('KARMA_XPU_DISABLE_OPTIX_DEVICE')
    upgrade(stage)
    import simple_workflow
    result=simple_workflow.organize(stage)
    if isinstance(result,tuple):stage,out=result
    out=hou.node(stage.userData('b2h_preview_node'))
    out.setDisplayFlag(True);stage.setDisplayFlag(False);out.setSelected(True,clear_all_selected=True)
    if hou.isUIAvailable():
        for p in hou.ui.paneTabs():
            if isinstance(p,hou.NetworkEditor):p.setPwd(hou.node('/stage'));p.homeToSelection()
            if isinstance(p,hou.SceneViewer):
                p.setPwd(hou.node('/stage'));p.setHydraRenderer('Karma XPU')
                p.curViewport().settings().setDisplayTextures(True);p.curViewport().settings().showMaterials(True);p.curViewport().frameAll()
    return stage


