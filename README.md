# Blender2Houdini

Blender and Houdini bridge by Samsul Alam Niom (SAM).

## SAM v011 - 20261019

[Download the Windows installer ZIP](Blender2Houdini_SAM_v011_20261019/Blender2Houdini_SAM_v011_20261019_Installer.zip), extract it, and run `Install.cmd`. Separate Blender add-on and Houdini connector ZIPs are in the same folder.

[Installation and workflow](Blender2Houdini_SAM_v011_20261019/INSTALL_v011.txt)

- Select a parent Empty such as `Car_Main` and send its descendant meshes, or send props and full scenes with collections.
- One visible Houdini Geometry object per asset, with named SOP branches and editable part/group Transform SOPs using Blender origin pivots.
- Preserve unique part names, parent hierarchy, collection paths, UVs, supported PBR materials, units and relative transforms.
- Karma and MaterialX builders, texture-only updates, texture reconnection and exchange dependencies beside the HIP.
- One Solaris SOP Import per asset feeds the shared merge/material/light/render chain. OBJ world transforms reach Solaris through the internal world output.
- Static full-scene export supports meshes and basic cameras/lights.

Bone/skin animation, constraints, drivers, collection instances and arbitrary Cycles shader graphs are not fully converted. No rig drivers are generated. Lighting translation is approximate.

## Validation

The v011 folder includes the recorded live import readback, test report and release ZIP SHA-256 checksums. The readback covers the single Geometry structure, 117 named parts, 109990 faces, UV presence, pivots, Solaris material bindings and node errors. It does not establish final rendered appearance or animated behavior. Packaging checks validate Python syntax, ZIP integrity and recorded checksums.

`prepare_release.py` and `package_release.py` package the versioned release. Generated scenes, models, exchange textures and Python caches are excluded from Git. Earlier v008 artifacts remain available in their version folder.
