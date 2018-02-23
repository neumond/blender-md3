[![Build Status](https://travis-ci.org/neumond/blender-md3.svg?branch=master)](https://travis-ci.org/neumond/blender-md3)

# .MD3 support for Blender

Up-to-date addon (Blender ≥ 2.7.2 supported!) for working with Quake 3 model format, written from scratch.

Can deal with animation (via the Shape Keys), textures and md3 tags (added as Empty objects).

More info on [BlenderWiki](http://wiki.blender.org/index.php/Extensions:2.6/Py/Scripts/Import-Export/MD3).

Used [this](http://www.icculus.org/homepages/phaethon/q3a/formats/md3format.html) format reference.

## Supported versions

2.6.9 very likely will work, though it becomes increasingly complex to test & maintain
python 3.3 builds due to lack of features present in newer versions of python and
significant API mismatches in bunch of supporting software.
