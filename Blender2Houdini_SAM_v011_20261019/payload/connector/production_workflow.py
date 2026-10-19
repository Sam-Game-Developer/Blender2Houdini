"""SAM v001: non-destructive SOP preparation and modular Solaris assembly."""
import hou, json, re
from pathlib import Path

def safe(value):
    value=re.sub(r'[^A-Za-z0-9_]', '_', value)
    return ('asset_'+value) if value[:1].isdigit() else value

def organize(stage):
    if stage.userData('b2h_workflow')=='1':return expose_shot(stage)
    data=json.loads(Path(stage.userData('b2h_manifest')).read_text())
    records={o['name']:o for o in data.get('objects',[])}
    def source_path(name,seen=None):
        seen=set() if seen is None else seen
        if name in seen:raise ValueError('Source parent cycle: '+name)
        seen.add(name);parent=records.get(name,{}).get('parent')
        return (source_path(parent,seen)+'/' if parent in records else '')+safe(name)
    imports=[n for n in stage.children() if n.type().name()=='sopimport']
    bypart={n.userData('b2h_partname'):n for n in imports}
    assignments=stage.node('ASSIGN_PBR');lib=stage.node('PBR_MATERIALX')
    holders=[];source_roots=set()
    categories={}
    for category in ['01_ENVIRONMENT','02_PROPS','03_CHARACTERS','04_FX']:
        node=hou.node('/obj').node(category)
        if node and node.userData('b2h_category')!=category:
            raise ValueError('Reserved category already belongs to another workflow: '+node.path())
        node=node or hou.node('/obj').createNode('subnet',category)
        node.setUserData('b2h_category',category);categories[category]=node
    prep=categories['02_PROPS'].createNode('subnet','SOP_PREP_'+stage.name())
    prep.setUserData('b2h_manifest',stage.userData('b2h_manifest'))
    for i,part in enumerate(data['parts'],1):
        imp=bypart[part['name']];om=hou.node(imp.parm('soppath').eval())
        holder=om.parent();source=hou.node(om.parm('objpath1').eval())
        ancestor=source.parent()
        while ancestor.parent()!=hou.node('/obj'):ancestor=ancestor.parent()
        source_roots.add(ancestor)
        prim='/World/PROPS/'+safe(stage.name())+'/'+source_path(part['source'])+'/'+safe(part['name'])
        imp.parm('primpath').set(prim);imp.parm('pathprefix').set(prim)
        assignments.parm('primpattern%d'%i).set(prim+'/**')
        # Existing source UVs/normals/topology are preserved, not recomputed.
        previous=om
        for label in ['CLEANUP_PRESERVE','NORMALS_PRESERVE','UV_PRESERVE']:
            node=holder.createNode('null',label);node.setInput(0,previous)
            node.setComment('Pass-through: preserve source data. Edit here when needed.');previous=node
        metadata=holder.createNode('attribwrangle','NAME_PATH_ATTRIBUTES');metadata.setInput(0,previous)
        metadata.parm('class').set(1)
        metadata.parm('snippet').set('s@name = '+json.dumps(part['source'])+'; s@blender_original_name = '+json.dumps(part['source'])+'; s@blender_parent = '+json.dumps(records.get(part['source'],{}).get('parent') or '')+'; i@blender_order = '+str(records.get(part['source'],{}).get('order',0))+';')
        out=holder.createNode('null','OUT_PROPS');out.setInput(0,metadata);out.setDisplayFlag(True);out.setRenderFlag(True)
        holders.append((holder,imp,source.path()))
    # Move only nodes owned by this import; update all absolute SOP references.
    for source_root in source_roots:
        original=source_root.path()
        moved=hou.moveNodesTo((source_root,),categories['02_PROPS'])[0]
        moved.setName('FBX_IMPORT_'+stage.name(),unique_name=True)
        for holder,imp,source_path_value in holders:
            holder.node('FBX_WORLD').parm('objpath1').set(source_path_value.replace(original,moved.path(),1))
    for holder,imp,_ in holders:
        moved=hou.moveNodesTo((holder,),prep)[0];moved.setDisplayFlag(False)
        imp.parm('soppath').set(moved.node('OUT_PROPS').path());moved.layoutChildren()
    prep.setDisplayFlag(False);prep.layoutChildren()
    categories['02_PROPS'].layoutChildren()
    sections={}
    previous=None
    for label in ['01_IMPORT','02_LOOKDEV','03_LAYOUT','04_LIGHTING','05_CAMERA','06_RENDER']:
        section=stage.createNode('subnet',label)
        if previous:section.setInput(0,previous)
        sections[label]=section;previous=section
    def output(section,last):
        section.node('output0').setInput(0,last);section.layoutChildren()
    moved=hou.moveNodesTo(tuple(imports),sections['01_IMPORT'])
    previous=None
    for node in moved:
        node.setInput(0,previous or sections['01_IMPORT'].indirectInputs()[0]);previous=node
    output(sections['01_IMPORT'],previous)
    lib,assignments=hou.moveNodesTo((lib,assignments),sections['02_LOOKDEV'])
    lib.setInput(0,sections['02_LOOKDEV'].indirectInputs()[0]);assignments.setInput(0,lib)
    output(sections['02_LOOKDEV'],assignments)
    for label,node_name in [('03_LAYOUT','ASSET_PLACEMENT'),('05_CAMERA','ACTIVE_RENDER_CAMERA')]:
        node=sections[label].createNode('null',node_name);node.setInput(0,sections[label].indirectInputs()[0])
        node.setComment('Reserved pass-through; no source camera/layout is fabricated.')
        output(sections[label],node)
    dome=hou.node(stage.userData('b2h_preview_node'))
    if dome and dome.type().name().split('::')[0]=='domelight':dome=hou.moveNodesTo((dome,),sections['04_LIGHTING'])[0]
    else:dome=sections['04_LIGHTING'].createNode('null','LIGHTING_INPUT')
    dome.setInput(0,sections['04_LIGHTING'].indirectInputs()[0]);output(sections['04_LIGHTING'],dome)
    karma=sections['06_RENDER'].createNode('karma','KARMA_RENDER_SETTINGS')
    karma.setInput(0,sections['06_RENDER'].indirectInputs()[0]);karma.parm('engine').set('xpu')
    output(sections['06_RENDER'],karma)
    final=stage.createNode('null','OUT_FINAL_STAGE');final.setInput(0,sections['06_RENDER'])
    rop=sections['06_RENDER'].createNode('usdrender_rop','USD_RENDER_ROP')
    rop.parm('loppath').set(final.path())
    stage.node('output0').setInput(0,final)
    alias=stage.node('OUT_KARMA');alias.setInput(0,final);alias.setDisplayFlag(False)
    alias.setComment('Compatibility output for existing bridge clients.')
    stage.setUserData('b2h_preview_node',final.path());stage.setUserData('b2h_workflow','1')
    for i,section in enumerate(sections.values()):section.setPosition(hou.Vector2(0,-i*2))
    final.setPosition(hou.Vector2(0,-12));alias.setPosition(hou.Vector2(4,-12))
    final.setDisplayFlag(True);final.cook(force=True)
    if final.errors():raise ValueError(str(final.errors()))
    return expose_shot(stage)

def expose_shot(asset):
    """Keep artist-facing light/camera/render nodes directly at /stage."""
    top=hou.node('/stage')
    if asset.userData('b2h_shot_exposed')=='1':
        light=hou.node(asset.userData('b2h_light_node'));light.setInput(0,assemble_assets(asset))
        final=hou.node(asset.userData('b2h_preview_node'))
        for node in [light,final]:node.setUserData('b2h_managed_stage',asset.path())
        return final
    sections={key:asset.node(key) for key in ['04_LIGHTING','05_CAMERA','06_RENDER']}
    dome=next((n for n in sections['04_LIGHTING'].children() if n.type().name().split('::')[0]=='domelight'),None)
    light=top.node('04_LIGHTING_DOME')
    if light and light.userData('b2h_shot')!='1':raise ValueError('Shot light name is already in use')
    if not light:
        light=hou.moveNodesTo((dome,),top)[0] if dome else top.createNode('domelight','04_LIGHTING_DOME')
        light.setName('04_LIGHTING_DOME');light.setUserData('b2h_shot','1')
    light.setInput(0,asset)
    camera=top.node('05_CAMERA')
    if camera and camera.userData('b2h_shot')!='1':raise ValueError('Shot camera name is already in use')
    if not camera:
        camera=top.createNode('camera','05_CAMERA');camera.setUserData('b2h_shot','1')
        camera.parm('primpath').set('/cameras/B2H_RENDER_CAMERA')
        viewer=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer) if hou.isUIAvailable() else None
        if viewer:
            view=viewer.curViewport().viewTransform();camera.parmTuple('t').set(view.extractTranslates());camera.parmTuple('r').set(view.extractRotates())
        else:camera.parmTuple('t').set((0,3,12))
        camera.setComment('Bridge preview camera; source FBX camera was not imported. Editable here.')
    camera.setInput(0,light)
    settings=top.node('06_KARMA_RENDER_SETTINGS')
    if not settings:
        settings=hou.moveNodesTo((sections['06_RENDER'].node('KARMA_RENDER_SETTINGS'),),top)[0]
        settings.setName('06_KARMA_RENDER_SETTINGS');settings.setUserData('b2h_shot','1')
    elif settings.userData('b2h_shot')!='1':raise ValueError('Shot render settings name is already in use')
    settings.setInput(0,camera);settings.parm('engine').set('xpu');settings.parm('camera').set('/cameras/B2H_RENDER_CAMERA')
    final=top.node('OUT_FINAL_STAGE')
    if not final:final=top.createNode('null','OUT_FINAL_STAGE');final.setUserData('b2h_shot','1')
    elif final.userData('b2h_shot')!='1':raise ValueError('Final stage name is already in use')
    final.setInput(0,settings)
    rop=top.node('USD_RENDER_ROP')
    if not rop:
        rop=hou.moveNodesTo((sections['06_RENDER'].node('USD_RENDER_ROP'),),top)[0]
        rop.setName('USD_RENDER_ROP');rop.setUserData('b2h_shot','1')
    elif rop.userData('b2h_shot')!='1':raise ValueError('Render output name is already in use')
    rop.parm('loppath').set(final.path())
    asset.node('OUT_FINAL_STAGE').setInput(0,asset.node('03_LAYOUT'))
    for section in sections.values():section.destroy()
    asset.setUserData('b2h_preview_node',final.path());asset.setUserData('b2h_light_node',light.path());asset.setUserData('b2h_shot_exposed','1')
    assembly=assemble_assets(asset);light.setInput(0,assembly)
    for i,node in enumerate([light,camera,settings,final],2):
        node.setPosition(hou.Vector2(8,-i*2));node.setUserData('b2h_managed_stage',asset.path())
    rop.setPosition(hou.Vector2(12,-8));rop.setUserData('b2h_managed_stage',asset.path())
    final.setDisplayFlag(True);asset.setDisplayFlag(False)
    return final

def assemble_assets(active):
    top=hou.node('/stage')
    assets=[n for n in top.children() if n.type().name()=='subnet' and n.userData('b2h_verified')=='1']
    merge=top.node('MERGE_ASSETS') or top.createNode('merge','MERGE_ASSETS')
    merge.setUserData('b2h_shot','1');merge.setUserData('b2h_managed_stage',active.path())
    empty=top.node('EMPTY_ASSET_BRANCH') or top.createNode('null','EMPTY_ASSET_BRANCH')
    empty.setUserData('b2h_shot','1')
    def sources(node):
        data=json.loads(Path(node.userData('b2h_manifest')).read_text())
        return {p['source'] for p in data['parts']}
    new=not bool(active.parm('b2h_include_scene'))
    if new:
        new_sources=sources(active)
        for old in assets:
            if old!=active and old.parm('b2h_include_scene') and old.parm('b2h_include_scene').eval() and sources(old)<=new_sources:
                old.parm('b2h_include_scene').set(False)
    occupied=set().union(*(sources(n) for n in assets if n!=active and n.parm('b2h_include_scene') and n.parm('b2h_include_scene').eval()))
    for i,asset in enumerate(assets):
        if not asset.parm('b2h_include_scene'):
            ptg=asset.parmTemplateGroup()
            enabled=asset==active and not bool(sources(asset)&occupied)
            ptg.append(hou.ToggleParmTemplate('b2h_include_scene','Include in Render Assembly',default_value=enabled))
            note='Active imported asset' if enabled else 'Previous import / test / overlapping source: disabled to avoid duplicate geometry'
            ptg.append(hou.StringParmTemplate('b2h_assembly_note','Assembly Status',1,default_value=(note,)))
            asset.setParmTemplateGroup(ptg)
        if not asset.userData('b2h_workflow'):
            output=asset.node('output0');out=asset.node('OUT_KARMA')
            if output and out:output.setInput(0,out)
        gate=top.node('INCLUDE_'+asset.name()) or top.createNode('switch','INCLUDE_'+asset.name())
        gate.setUserData('b2h_shot','1');gate.setInput(0,empty);gate.setInput(1,asset)
        gate.parm('input').setExpression('ch("'+asset.parm('b2h_include_scene').path()+'")',hou.exprLanguage.Hscript)
        gate.setComment('0 = exclude, 1 = include. Controlled on the asset subnet.')
        merge.setInput(i,gate);asset.setPosition(hou.Vector2(i*4,2));gate.setPosition(hou.Vector2(i*4,0))
    empty.setPosition(hou.Vector2(-4,0));merge.setPosition(hou.Vector2(8,-2))
    return merge
