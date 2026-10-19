"""Native Karma / USD MaterialX builders for Blender Principled PBR."""
import hou, json, re
from pathlib import Path
EXTRA_PBR = {'coat': 'coat', 'coat_roughness': 'coat_roughness', 'coat_ior': 'coat_IOR', 'anisotropy': 'specular_anisotropy', 'anisotropy_rotation': 'specular_rotation', 'sheen': 'sheen', 'sheen_roughness': 'sheen_roughness', 'subsurface': 'subsurface', 'subsurface_scale': 'subsurface_scale', 'diffuse_roughness': 'diffuse_roughness'}

def validate_mode(mode):
    if mode not in ('karma','materialx'): raise ValueError('Unknown material builder: '+str(mode))
    return mode

def build_material(lib, name, mat, package, mode='karma'):
    import voptoolutils
    from houdini_importer import portable
    validate_mode(mode)
    mask=voptoolutils.KARMAMTLX_TAB_MASK if mode=='karma' else voptoolutils.MTLX_TAB_MASK
    sub=voptoolutils._setupMtlXBuilderSubnet(destination_node=lib,name=name,mask=mask,
        folder_label='Karma Material Builder' if mode=='karma' else 'USD MaterialX Builder',
        render_context='kma' if mode=='karma' else 'mtlx')
    try:
        shader=sub.node('mtlxstandard_surface'); shader.setName('PBR')
        shader.parmTuple('base_color').set(mat['base_color'])
        shader.parm('specular_roughness').set(mat['roughness']); shader.parm('metalness').set(mat['metallic'])
        shader.parm('transmission').set(mat.get('transmission',0));shader.parm('specular_IOR').set(mat.get('ior',1.5));shader.parmTuple('opacity').set((mat.get('alpha',1),)*3)
        shader.parm('emission').set(mat.get('emission_strength',0));shader.parmTuple('emission_color').set(mat.get('emission',[0,0,0]))
        for key,value in mat.get('extra_pbr',{}).items():
            if key in EXTRA_PBR and shader.parm(EXTRA_PBR[key]):shader.parm(EXTRA_PBR[key]).set(value)
        for key,tex in mat['maps'].items():
            img=sub.createNode('mtlximage',key)
            img.parm('signature').set('default' if key in ['roughness','metallic','transmission'] or key in EXTRA_PBR else 'color3')
            img.parm('file').set(portable(package / tex['path']))
            img.parm('filecolorspace').set('sRGB' if key in ['base_color','emission'] and tex['colorspace']=='sRGB' else 'raw')
            if key=='normal':
                normal=sub.createNode('mtlxnormalmap','NORMAL_MAP')
                normal.setNamedInput('in',img,0); normal.parm('scale').set(mat.get('normal_strength',1))
                shader.setNamedInput('normal',normal,0)
            else:
                value=img
                for op in tex.get('operations',[]):
                    node=sub.createNode({'invert':'mtlxinvert','clamp':'mtlxclamp','luminance':'mtlxluminance'}[op['op']],key+'_'+op['op'])
                    if op['op']!='luminance':node.parm('signature').set('color3')
                    if op['op']=='clamp':node.parm('low').set(op['min']);node.parm('high').set(op['max'])
                    node.setNamedInput('in',value,0);value=node
                    node.setUserData('b2h_operation',__import__('json').dumps(op))
                target=EXTRA_PBR[key] if key in EXTRA_PBR else {'base_color':'base_color','roughness':'specular_roughness','metallic':'metalness','transmission':'transmission','alpha':'opacity','emission':'emission_color'}[key]
                shader.setNamedInput(target,value,0)
        sub.layoutChildren(); sub.setComment(mat['name']); sub.setGenericFlag(hou.nodeFlag.DisplayComment,True)

        sub.setUserData('b2h_builder',mode)
        sub.setUserData('b2h_source_material',mat['name'])
        return sub
    except Exception:
        sub.destroy()
        raise

def _selected_geometries(nodes):
    result=[]
    for node in nodes:
        if node.userData('b2h_asset_root'):
            if node.userData('b2h_parent_layout')=='objects':
                result.extend(n for n in node.children() if n.userData('b2h_native_part')=='1' and n not in result)
                continue
            geo=node.node('GEOMETRY')
            if geo and geo not in result:result.append(geo)
            continue
        current=node
        while current and not current.userData('b2h_live_geometry'): current=current.parent()
        if current and current not in result: result.append(current)
        elif node.type().name()=='sopimport' and node.parm('soppath'):
            sop=hou.node(node.userData('b2h_asset_geometry')) if node.userData('b2h_asset_geometry') else hou.node(node.parm('soppath').eval())
            if sop and sop.userData('b2h_asset_root') and sop.userData('b2h_parent_layout')=='objects':
                result.extend(n for n in sop.children() if n.userData('b2h_native_part')=='1' and n not in result)
                continue
            if sop and sop.userData('b2h_live_geometry'):
                if sop not in result:result.append(sop)
                continue
            if sop and sop.parent().userData('b2h_live_geometry') and sop.parent() not in result: result.append(sop.parent())
    if not result: raise ValueError('Select imported OBJ Geometry or its Solaris SOP Import first')
    return result

def use_selected(mode, nodes=None):
    """Build each variant once from exported Blender PBR, then switch bindings.
    Cached variants retain user shader edits. Original source graphs are retained.
    """
    validate_mode(mode)
    geos=_selected_geometries(nodes if nodes is not None else hou.selectedNodes())
    lib=hou.node('/stage/MATERIAL_LIBRARY'); assign=hou.node('/stage/ASSIGN_MATERIALS')
    if not lib or not assign: raise ValueError('Bridge Material Library / Assign Materials missing')
    plan=[]
    for geo in geos:
        manifest=Path(geo.userData('b2h_manifest'))
        data=json.loads(manifest.read_text(encoding='utf-8'))
        part_names=set(json.loads(geo.userData('b2h_part_sops') or '{}'))
        parts=[p for p in data['parts'] if p['name'] in part_names] if geo.userData('b2h_collection_container')=='1' else [p for p in data['parts'] if p['source']==geo.userData('b2h_live_geometry')]
        mats=json.loads(geo.userData('b2h_material_nodes') or '{}')
        paths={}
        for sop in geo.allSubChildren():
            if sop.userData('b2h_partname'):
                g=sop.geometry()
                paths[sop.userData('b2h_partname')]=set(g.primStringAttribValues('path'))
        if not parts or any(p['name'] not in paths for p in parts): raise ValueError('Missing bridge part metadata: '+geo.path())
        for mid in {p['material'] for p in parts}:
            for tex in data['materials'][mid]['maps'].values():
                if not (manifest.parent/tex['path']).is_file(): raise ValueError('Missing texture: '+tex['path'])
        plan.append((geo,manifest,data,parts,mats,paths))
    count=0
    with hou.undos.group('Blender2Houdini Use '+mode):
        for geo,manifest,data,parts,mats,paths in plan:
            variant_paths={}
            for mid in sorted({p['material'] for p in parts}):
                name=re.sub('[^A-Za-z0-9_]','_',manifest.parent.name+'_'+mid+'_'+mode)
                sub=lib.node(name)
                if sub and sub.userData('b2h_builder')!=mode: raise ValueError('Unmanaged shader name collision: '+name)
                if not sub:
                    sub=build_material(lib,name,data['materials'][mid],manifest.parent,mode)
                    sub.setUserData('b2h_manifest',str(manifest))
                    n=lib.parm('materials').eval()+1;lib.parm('materials').set(n)
                    lib.parm('matnode%d'%n).set(name)
                    lib.parm('matpath%d'%n).set('/materials/B2H/'+name)
                n=next(i for i in range(1,lib.parm('materials').eval()+1) if lib.parm('matnode%d'%i).eval() in (name,sub.path()))
                variant_paths[mid]=lib.parm('matpath%d'%n).eval()
                old=mats.get(mid)
                for wrangle in geo.allSubChildren():
                    if wrangle.parm('snippet') and old:
                        wrangle.parm('snippet').set(wrangle.parm('snippet').eval().replace(json.dumps(old),json.dumps(sub.path())))
                mats[mid]=sub.path();count+=1
            for part in parts:
                patterns={path+' '+path+'/**' for path in paths[part['name']]}
                matches=[i for i in range(1,assign.parm('nummaterials').eval()+1) if assign.parm('primpattern%d'%i).eval() in patterns]
                if not matches: raise ValueError('Material binding row missing: '+part['name'])
                for i in matches: assign.parm('matspecpath%d'%i).set(variant_paths[part['material']])
            geo.setUserData('b2h_material_nodes',json.dumps(mats));geo.setUserData('b2h_builder',mode)
        lib.layoutChildren()
    report='Using '+('Karma Material Builder' if mode=='karma' else 'USD MaterialX Builder')+': %d objects, %d materials'%(len(geos),count)
    if hou.isUIAvailable(): hou.ui.setStatusMessage(report)
    return report
