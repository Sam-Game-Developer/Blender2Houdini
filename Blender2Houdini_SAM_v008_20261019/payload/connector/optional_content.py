from pathlib import Path
import sys
from bridge_config import settings
def open_library():
    root=Path(settings().get('content_library',''))
    script=root/'install.py'
    if not script.is_file():raise ValueError('Existing BCGI Content Library not selected. Run the installer and choose its folder.')
    sys.path.insert(0,str(root))
    exec(compile(script.read_text(encoding='utf-8-sig'),str(script),'exec'),{'__file__':str(script),'__name__':'__main__'})
