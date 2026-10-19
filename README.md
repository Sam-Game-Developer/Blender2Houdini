# Blender2Houdini

Blender and Houdini bridge by Samsul Alam Niom (SAM).

## SAM v008 - 20261019

[Download the Windows installer ZIP](Blender2Houdini_SAM_v008_20261019/Blender2Houdini_SAM_v008_20261019_Installer.zip), extract it, and run `Install.cmd`. Separate Blender add-on and Houdini connector ZIPs are in the same version folder.

[Installation and supported features](Blender2Houdini_SAM_v008_20261019/INSTALL_v008.txt)

- Send Car / Object, Send Props, and Send Full Scene + Collections from Blender.
- One Houdini Geometry container per asset; nested SOP subnets follow Blender collections.
- Preserve unique part names, collection paths, existing UVs, materials and relative transforms.
- Karma and MaterialX material builders, texture-only updates, and texture reconnection.
- Full-scene export supports static meshes and basic cameras/lights.

Rigs, animation, constraints, collection instances, and arbitrary Cycles shader graphs are not fully converted. Lighting translation is approximate.

## Validation

The version folder includes recorded isolated Blender/Houdini test results and ZIP SHA-256 checksums. Collection hierarchy, UVs, materials, scale, pivots, resend deduplication and mesh round-trip were checked. These checks do not establish final rendered appearance or installation in the user's currently open apps.

`prepare_release.py` and `finalize_release.py` package the versioned release. DCC regression scripts require Blender/Houdini and use local fixture paths; adapt those paths for another machine. Generated scene files, models, exchange textures and Python caches are excluded from Git.
