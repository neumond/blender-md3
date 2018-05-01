from contextlib import contextmanager
from math import sqrt

from PIL import Image, ImageChops

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


def rmsdiff(im1, im2):
    "Calculate the root-mean-square difference between two images"
    h = ImageChops.difference(im1, im2).histogram()
    return sqrt(
        sum(map(lambda h, i: h*(i**2), h, range(256)))
        /
        (im1.size[0] * im1.size[1]),
    )


def compare_images(a, b):
    img_a = Image.open(str(a))
    img_b = Image.open(str(b))
    assert img_a.size == img_b.size
    assert rmsdiff(img_a, img_b) < 10


def test_render(testdir, tmpdir, simple_blend):
    img_a = testdir / 'a.png'
    img_b = testdir / 'b.png'

    render_to_file(img_a)

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

    render_to_file(img_b)

    compare_images(img_a, img_b)
