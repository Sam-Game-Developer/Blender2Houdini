from pathlib import Path
import ast,zipfile
ROOT=Path(__file__).resolve().parent
for p in (ROOT/'payload').rglob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
addon=ROOT/'payload'/'blender2houdini_sam'
with zipfile.ZipFile(ROOT/(ROOT.name+'_BlenderAddon.zip'),'w',zipfile.ZIP_DEFLATED) as z:
 for p in addon.rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts:z.write(p,'blender2houdini_sam/'+p.relative_to(addon).as_posix())
print('SOURCE_PARSE_AND_ADDON_ZIP_PASS')
