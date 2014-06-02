# This script is licensed as public domain.

# TODO: different normals for shape keys
# TODO: merge vertices near sharp edges (there is a disconnected surface now)
# TODO: use_smooth=False for flat faces (all vertex normal equal)

bl_info = {
    "name": "Import Quake 3 Model (.md3)",
    "author": "Vitalik Verhovodov",
    "version": (0, 0, 0),
    "blender": (2, 6, 9),
    "location": "File > Import > Quake 3 Model",
    "description": "Import to the Quake 3 Model format (.md3)",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}

import bpy
import mathutils
import struct
from bpy_extras.io_utils import ImportHelper
from math import pi, sin, cos
import os.path


def read_struct_from_file(file, fmt):
    return struct.unpack(fmt, file.read(struct.calcsize(fmt)))


def cleanup_string(b):
    return b.replace(b'\0', b'').decode('utf-8')


def read_n_items(ctx, file, n, offset, func):
    file.seek(offset)
    for i in range(n):
        func(ctx, i, file)


def read_frame(ctx, i, file):
    b = read_struct_from_file(file, '<3f3f3f')
    min_bounds, max_bounds, local_origin = (b[k:k+3] for k in range(0, 9, 3))
    bounding_sphere_radius, frame_name = read_struct_from_file(file, '<f16s')
    ctx['frameName{}'.format(i)] = cleanup_string(frame_name)


def read_tag(ctx, i, file):
    name = read_struct_from_file(file, '<64s')[0]
    b = read_struct_from_file(file, '<3f3f3f3f')
    o = [None, None, None]
    origin, o[0], o[1], o[2] = (b[k:k+3] for k in range(0, 12, 3))
    bpy.ops.object.add(type='EMPTY')
    tag = bpy.context.object
    tag.name = cleanup_string(name)
    tag.empty_draw_type = 'ARROWS'
    tag.location = mathutils.Vector(origin)
    o = [mathutils.Vector(item) for item in o]
    tag.scale = mathutils.Vector(tuple(item.length for item in o))
    for item in o:
        item.normalize()
    mx = mathutils.Matrix()
    for j in range(3):
        mx[j].xyz = o[j]
    tag.rotation_euler = mx.to_euler()  # TODO: use tag.matrix_basis?


def guess_texture_filepath(modelpath, imagepath):
    fileexts = ('', '.png', '.tga', '.jpg', '.jpeg')
    modelpath = os.path.normpath(os.path.normcase(modelpath))
    modeldir, _ = os.path.split(modelpath)
    imagedir, imagename = os.path.split(os.path.normpath(os.path.normcase(imagepath)))
    previp = None
    ip = imagedir
    while ip != previp:
        if ip in modeldir:
            pos = modeldir.rfind(ip)
            nameguess = os.path.join(modeldir[:pos + len(ip)], imagedir[len(ip):], imagename)
            for ext in fileexts:
                yield nameguess + ext
        previp = ip
        ip, _ = os.path.split(ip)
    nameguess = os.path.join(modeldir, imagename)
    for ext in fileexts:
        yield nameguess + ext


def read_surface_shader(ctx, i, file):
    name, index = read_struct_from_file(file, '<64si')
    name = cleanup_string(name)

    texture = bpy.data.textures.new(name, 'IMAGE')
    texture_slot = ctx['material'].texture_slots.create(i)
    texture_slot.uv_layer = 'UVMap'
    texture_slot.use = True
    texture_slot.texture_coords = 'UV'
    texture_slot.texture = texture

    for fname in guess_texture_filepath(ctx['filename'], name):
        if os.path.isfile(fname):
            image = bpy.data.images.load(fname)
            texture.image = image
            break


def read_surface_triangle(ctx, i, file):
    a, b, c = read_struct_from_file(file, '<3i')
    ls = i * 3
    ctx['mesh'].loops[ls].vertex_index = a
    ctx['mesh'].loops[ls + 1].vertex_index = c  # swapped
    ctx['mesh'].loops[ls + 2].vertex_index = b  # swapped
    ctx['mesh'].polygons[i].loop_start = ls
    ctx['mesh'].polygons[i].loop_total = 3
    ctx['mesh'].polygons[i].use_smooth = True


def read_surface_ST(ctx, i, file):
    s, t = read_struct_from_file(file, '<ff')
    # store in context, these values used more than once
    ctx['uv'].append((s, 1.0 - t))  # inverted t


def make_surface_UV_map(ctx):
    for poly in ctx['mesh'].polygons:
        for i in range(poly.loop_start, poly.loop_start + poly.loop_total):
            vidx = ctx['mesh'].loops[i].vertex_index
            ctx['uvdata'][i].uv = ctx['uv'][vidx]


def decode_normal(b):
    lat = b[0] / 255.0 * 2 * pi
    lon = b[1] / 255.0 * 2 * pi
    x = cos(lat) * sin(lon)
    y = sin(lat) * sin(lon)
    z = cos(lon)
    return (x, y, z)


vert_size = struct.calcsize('<hhh2s')
def read_surface_vert(ctx, i, file):
    x, y, z, n = read_struct_from_file(file, '<hhh2s')
    ctx['verts'][i].co = mathutils.Vector((x / 64.0, y / 64.0, z / 64.0))


def read_surface_normals(ctx, i, file):
    x, y, z, n = read_struct_from_file(file, '<hhh2s')
    ctx['verts'][i].normal = mathutils.Vector(decode_normal(n))


def read_surface(ctx, i, file):
    start_pos = file.tell()

    magic, name, flags, nFrames, nShaders, nVerts, nTris, offTris, offShaders, offST, offVerts, offEnd =\
        read_struct_from_file(file, '<4s64siiiiiiiiii')
    assert magic == b'IDP3'
    assert nFrames == ctx['modelFrames']
    assert nShaders <= 256
    assert nVerts <= 4096
    assert nTris <= 8192

    ctx['mesh'] = bpy.data.meshes.new(cleanup_string(name))
    ctx['mesh'].vertices.add(count=nVerts)
    ctx['mesh'].polygons.add(count=nTris)
    ctx['mesh'].loops.add(count=nTris*3)

    read_n_items(ctx, file, nTris, start_pos + offTris, read_surface_triangle)

    ctx['test_normals'] = {}
    ctx['verts'] = ctx['mesh'].vertices
    read_n_items(ctx, file, nVerts, start_pos + offVerts, read_surface_vert)

    ctx['mesh'].update(calc_edges=True)
    ctx['mesh'].validate()

    # separate step for normals. update() causes recalculation
    read_n_items(ctx, file, nVerts, start_pos + offVerts, read_surface_normals)

    ctx['material'] = bpy.data.materials.new('Main')
    ctx['mesh'].materials.append(ctx['material'])

    ctx['mesh'].uv_textures.new('UVMap')
    ctx['uv'] = []
    read_n_items(ctx, file, nVerts, start_pos + offST, read_surface_ST)
    ctx['uvdata'] = ctx['mesh'].uv_layers['UVMap'].data
    make_surface_UV_map(ctx)

    read_n_items(ctx, file, nShaders, start_pos + offShaders, read_surface_shader)

    obj = bpy.data.objects.new(cleanup_string(name), ctx['mesh'])
    ctx['context'].scene.objects.link(obj)

    if nFrames > 1:
        obj.shape_key_add(name=ctx['frameName0'] + 'first')  # adding first frame, which is already loaded
        ctx['mesh'].shape_keys.use_relative = False
        # TODO: check MD3 has linear frame interpolation
        for frame in range(1, nFrames):  # first frame skipped
            shape_key = obj.shape_key_add(name=ctx['frameName{}'.format(frame)])
            ctx['verts'] = shape_key.data
            read_n_items(ctx, file, nVerts, start_pos + offVerts + frame * vert_size * nVerts, read_surface_vert)
        bpy.context.scene.objects.active = obj
        bpy.context.object.active_shape_key_index = 0
        bpy.ops.object.shape_key_retime()
        for frame in range(nFrames):
            ctx['mesh'].shape_keys.eval_time = 10.0 * (frame + 1)
            ctx['mesh'].shape_keys.keyframe_insert('eval_time', frame=frame)

    file.seek(start_pos + offEnd)


def importMD3(context, filename):
    with open(filename, 'rb') as file:
        magic, version, modelname, flags, nFrames, nTags, nSurfaces,\
        nSkins, offFrames, offTags, offSurfaces, offEnd\
            = read_struct_from_file(file, '<4si64siiiiiiiii')
        assert magic == b'IDP3'
        assert version == 15
        ctx = {'context': context, 'modelFrames': nFrames, 'filename': filename}

        bpy.ops.scene.new()
        context.scene.name = cleanup_string(modelname)
        context.scene.frame_start = 0
        context.scene.frame_end = nFrames - 1

        read_n_items(ctx, file, nFrames, offFrames, read_frame)
        read_n_items(ctx, file, nTags, offTags, read_tag)
        read_n_items(ctx, file, nSurfaces, offSurfaces, read_surface)

        context.scene.frame_set(0)
        context.scene.game_settings.material_mode = 'GLSL'

        bpy.ops.object.lamp_add(type='SUN')


class ImportMD3(bpy.types.Operator, ImportHelper):
    '''Import a Quake 3 Model MD3 file'''
    bl_idname = "import.md3"
    bl_label = 'Import MD3'
    filename_ext = ".md3"

    def execute(self, context):
        importMD3(context, self.properties.filepath)
        return {'FINISHED'}

    def check(self, context):
        filepath = bpy.path.ensure_ext(self.filepath, '.md3')
        if filepath != self.filepath:
            self.filepath = filepath
            return True
        return False


def menu_func(self, context):
    self.layout.operator(ImportMD3.bl_idname, text="Quake 3 Model (.md3)")

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_import.append(menu_func)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_import.remove(menu_func)

if __name__ == "__main__":
    register()


