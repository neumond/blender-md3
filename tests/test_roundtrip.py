from contextlib import contextmanager

import bpy
from io_scene_md3.export_md3 import MD3Exporter
from io_scene_md3.import_md3 import MD3Importer


def render_to_file(path):
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(animation=False, write_still=True)


@contextmanager
def use_scene(scene):
    old_scene = bpy.context.screen.scene
    bpy.context.screen.scene = scene
    yield
    bpy.context.screen.scene = old_scene


def test_render(testdir, tmpdir):
    bpy.ops.wm.open_mainfile(filepath=str(testdir / 'simple.blend'))

    render_to_file(testdir / 't1.png')

    old_scene = bpy.context.scene

    fname = tmpdir / 'output.md3'
    MD3Exporter(bpy.context)(str(fname))
    MD3Importer(bpy.context)(str(fname))

    new_scene = bpy.context.scene
    assert old_scene is not new_scene

    # remove all lamps and cameras from new_scene
    # then make copies from old_scene to reproduce original rendering parameters
    bpy.ops.object.select_by_type(type='LAMP')
    bpy.ops.object.select_by_type(type='CAMERA', extend=True)
    bpy.ops.object.delete(use_global=False)

    with use_scene(old_scene):
        bpy.ops.object.select_by_type(type='LAMP')
        bpy.ops.object.select_by_type(type='CAMERA', extend=True)
        bpy.ops.object.make_links_scene(scene=new_scene.name)
        bpy.ops.object.select_all(action='DESELECT')

    new_scene.camera = old_scene.camera
    new_scene.world = old_scene.world

    render_to_file(testdir / 't2.png')
