import bpy

from io_scene_md3.export_md3 import MD3Exporter
from io_scene_md3.import_md3 import MD3Importer


def get_scene():
    return bpy.context.scene


def get_object():
    return get_scene().objects['Empty']


def walk_over_frames():
    scene = get_scene()
    for f in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(f)
        yield f


def matrix_to_flat_tuple(m):
    result = []
    for row in m:
        result.extend(row)
    return tuple(result)


def take_data():
    result = []
    for frame in walk_over_frames():
        obj = get_object()
        result.append(matrix_to_flat_tuple(obj.matrix_basis))
    return result


def compare_data(a, b):
    result = 0
    for at, bt in zip(a, b):
        dev = max(abs(bv - av) for av, bv in zip(at, bt))
        if dev > result:
            result = dev
    return result


def test_tag_animations(tmpdir, blend_opener):
    blend_opener('tags.blend')
    expected = take_data()

    old_scene = bpy.context.scene

    fname = tmpdir / 'tags.md3'
    MD3Exporter(bpy.context)(str(fname))
    MD3Importer(bpy.context)(str(fname))

    new_scene = bpy.context.scene
    assert old_scene is not new_scene

    got = take_data()

    assert compare_data(expected, got) < 1e-5
