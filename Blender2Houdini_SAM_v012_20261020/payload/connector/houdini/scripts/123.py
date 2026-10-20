"""Start the receiver when Houdini opens a new/empty scene."""
import os,sys
root=os.environ.get('B2H_SAM_ROOT')
if root:
    if root not in sys.path:sys.path.insert(0,root)
    import b2h_bootstrap
    b2h_bootstrap.defer_start()
