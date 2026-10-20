"""Native camera/light metadata for static full-scene sends."""
import hou,math
from collection_workflow import safe,converted_matrix

def apply(data,light,camera,settings):
    if data.get('export_mode')!='scene':return
    top=hou.node('/stage');last=light
    for entry in data.get('scene_extras',[]):
        if entry.get('hide_render'):continue
        if entry['type']=='CAMERA' and entry.get('projection') not in ('PERSP','ORTHO'):continue
        node=next((n for n in top.children() if n.userData('b2h_scene_extra')==entry['name']),None)
        node=node or top.createNode('camera' if entry['type']=='CAMERA' else 'light','BLENDER_'+safe(entry['name']))
        node.setUserData('b2h_scene_extra',entry['name']);node.parm('primpath').set('/'+('cameras' if entry['type']=='CAMERA' else 'lights')+'/Blender/'+safe(entry['name']))
        matrix=converted_matrix(entry['matrix_world'],data.get('unit_scale',1))
        node.parmTuple('t').set(tuple(matrix.extractTranslates()));node.parmTuple('r').set(tuple(matrix.extractRotates()))
        if entry['type']=='CAMERA':
            node.parm('focalLength').set(entry['lens']);node.parm('horizontalAperture').set(entry['sensor_width'])
            if node.parm('projection'):node.parm('projection').set('orthographic' if entry['projection']=='ORTHO' else 'perspective')
            if entry['projection']=='ORTHO':node.parm('horizontalAperture').set(entry['ortho_scale']*data.get('unit_scale',1)*10)
            if node.parmTuple('clippingRange'):node.parmTuple('clippingRange').set((entry['clip_start']*data.get('unit_scale',1),entry['clip_end']*data.get('unit_scale',1)))
            if entry.get('active'):settings.parm('camera').set(node.parm('primpath').eval())
        else:
            light_type={'AREA':'UsdLuxRectLight','SUN':'UsdLuxDistantLight','POINT':'UsdLuxSphereLight','SPOT':'UsdLuxSphereLight'}[entry['light_type']]
            node.parm('lighttype').set(light_type)
            for key,value in [('intensity',entry['energy']/(4*math.pi)),('color',tuple(entry['color'])),('width',entry['size']*data.get('unit_scale',1)),('height',entry['size_y']*data.get('unit_scale',1))]:
                prefix='inputs'+key+'_';control=next((p for p in node.parms() if prefix+'control' in p.name()),None)
                if control:control.set('set')
                if isinstance(value,tuple):
                    parm=next(t for t in node.parmTuples() if prefix in t.name() and 'control' not in t.name() and len(t)==len(value));parm.set(value)
                else:
                    parm=next(p for p in node.parms() if prefix in p.name() and 'control' not in p.name());parm.set(value)
            if entry['light_type']=='SPOT':
                parms=[p for p in node.parms() if 'inputsshapingconeangle_' in p.name() and 'control' not in p.name()]
                if parms:parms[0].set(math.degrees(entry['spot_size'])/2)
        node.setInput(0,last);node.setPosition(hou.Vector2(18,-2*len([n for n in top.children() if n.userData('b2h_scene_extra')])));last=node
    camera.setInput(0,last)
