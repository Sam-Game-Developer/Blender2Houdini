# Blender2Houdini

Blender and Houdini bridge by Samsul Alam Niom (SAM).

## SAM v012 - 20261020

[Download the Windows installer ZIP](Blender2Houdini_SAM_v012_20261020/Blender2Houdini_SAM_v012_20261020_Installer.zip), extract it, close Blender/Houdini and run `Install.cmd`. Install both updated components for the new transfer layout. Separate Blender add-on and Houdini connector ZIPs are in the same folder.

[Installation and workflow](Blender2Houdini_SAM_v012_20261020/INSTALL_v012.txt)

### Original texture filenames and Blender project folders

For `Sports_Car.blend`, the saved Houdini project receives:

```text
<HIP folder>/Blender2Houdini_Texture/
  Sports_Car/
    Body_BaseColor.png
    Body_Normal.png
    .b2h/<transfer id>/manifest.json
    .b2h/<transfer id>/meshes.fbx
```

- Original texture basenames and file bytes are retained, including packed image bytes. Generated images use their declared format.
- Model sends and Send Textures Only share this layout. Save the Blender file first; its file stem becomes the project folder name.
- Different sources with identical filenames use `duplicates/<source id>/<original filename>` so neither source overwrites the other. Sending the same source again updates its existing file.
- Texture-only sends accept a parent Empty and include its mesh descendants. Geometry is not rebuilt by texture-only reconnect.
- Receiver localization, texture-folder reconnect and HIP Save As collection preserve original filenames. Legacy manifests remain supported; existing historical textures are not renamed automatically.
- Before the HIP is saved, the configured inbox uses the same project folder layout.

### Bridge workflow

- Select a parent Empty such as `Car_Main` and send its descendant meshes, or send props and full scenes with collections.
- One visible Houdini Geometry object per asset, with named SOP branches and editable part/group Transform SOPs using Blender origin pivots.
- Preserve unique part names, parent hierarchy, collection paths, UVs, supported PBR materials, units and relative transforms.
- Karma and MaterialX builders, texture-only updates and texture reconnection.
- One Solaris SOP Import per asset feeds the shared merge/material/light/render chain; OBJ world transforms reach Solaris through the internal world output.

Bone/skin animation, constraints, drivers, collection instances and arbitrary Cycles shader graphs are not fully converted. No rig drivers are generated. Lighting translation is approximate.

## Validation

The v012 test suite passes 14 isolated filesystem/exporter/connector regressions, covering filenames, byte copies, collisions, packed/generated images, parent-Empty texture sends, legacy packages, localization and Save As/re-send. Blender and Houdini APIs are stubbed in these tests; a live v012 DCC transfer and final rendering were not run. `TEST_RESULTS.json` records this scope.

`prepare_release.py` and `package_release.py` check Python syntax, ZIP integrity and release SHA-256 checksums. Run `python test_texture_layout.py` to reproduce the isolated regressions. Generated scenes, models, exchange textures and Python caches are excluded from Git. Earlier v008/v011 artifacts remain in their version folders.
