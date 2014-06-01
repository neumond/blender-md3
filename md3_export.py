# This script is licensed as public domain.

# grouping to surfaces must done by UV maps
# TODO: merge surfaces with same uv maps and texture
# TODO: add assertions on maxcounts (vertex, tris, etc)

bl_info = {
    "name": "Export Quake 3 Model (.md3)",
    "author": "Vitalik Verhovodov",
    "version": (0, 0, 0),
    "blender": (2, 6, 9),
    "location": "File > Export > Quake 3 Model",
    "description": "Export to the Quake 3 Model format (.md3)",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}

import bpy
import mathutils
import struct
from bpy_extras.io_utils import ExportHelper
from math import atan2, acos, pi, sqrt


def write_struct_to_file(file, fmt, data):
    file.write(struct.pack(fmt, *data))


def write_delayed(ctx, file, name, fmt, default):
    if name in ctx['delayed']:
        raise Exception('Delayed tag {} is already allocated'.format(name))
    ctx['delayed'][name] = (file.tell(), fmt)
    write_struct_to_file(file, fmt, default)


def resolve_delayed(ctx, file, name, value):
    oldpos = file.tell()
    position, fmt = ctx['delayed'][name]
    file.seek(position)
    write_struct_to_file(file, fmt, value)
    file.seek(oldpos)
    del ctx['delayed'][name]


def write_n_items(ctx, file, n, func):
    for i in range(n):
        func(ctx, i, file)


def write_nm_items(ctx, file, n, m, func, pre_outerfunc, post_outerfunc):
    for i in range(n):
        pre_outerfunc(ctx, i, file)
        for j in range(m):
            func(ctx, i, j, file)
        post_outerfunc(ctx, i, file)


def write_frame(ctx, i, file):
    write_delayed(ctx, file, 'frame{}_min'.format(i), '<3f', (0.0, 0.0, 0.0))
    write_delayed(ctx, file, 'frame{}_max'.format(i), '<3f', (0.0, 0.0, 0.0))
    write_struct_to_file(file, '<3f', (0.0, 0.0, 0.0))  # local_origin
    write_delayed(ctx, file, 'frame{}_sphere'.format(i), '<f', (0.0,))
    write_struct_to_file(file, '<16s', (b'',))  # frame name, ignored


def write_tag(ctx, i, file):
    tag = bpy.context.scene.objects[ctx['tagNames'][i]]
    origin = tuple(tag.location)
    ox = tuple(tag.matrix_basis[0][:3])
    oy = tuple(tag.matrix_basis[1][:3])
    oz = tuple(tag.matrix_basis[2][:3])
    write_struct_to_file(file, '<64s12f', (tag.name.encode('utf-8'),) + origin + ox + oy + oz)


def gather_shader_info(mesh):
    uv_maps = {}
    for material in mesh.materials:
        for texture_slot in material.texture_slots:
            if texture_slot is None:
                continue
            if not texture_slot.use or not texture_slot.uv_layer or texture_slot.texture_coords != 'UV':
                continue
            uv_map_name = texture_slot.uv_layer
            if uv_map_name not in uv_maps:
                uv_maps[uv_map_name] = []
            if not texture_slot.texture or texture_slot.texture.type != 'IMAGE':
                continue
            uv_maps[uv_map_name].append(texture_slot.texture.image.filepath)
    uv_maps = [(k, v) for k, v in uv_maps.items()]
    if len(uv_maps) <= 0:
        print('Warning: No applicable shaders found')
        return None, []
    elif len(uv_maps) == 1:
        return uv_maps[0]
    else:
        print('Warning: Multiple UV maps found, only one will be chosen')
        return uv_maps[0]


def gather_vertices(mesh):
    md3vert_to_loop_map = []
    loop_to_md3vert_map = []
    index = {}
    for i, loop in enumerate(mesh.loops):
        key = (loop.vertex_index, tuple(loop.normal))
        md3id = index.get(key, None)
        if md3id is None:
            md3id = len(md3vert_to_loop_map)
            index[key] = md3id
            md3vert_to_loop_map.append(i)
        loop_to_md3vert_map.append(md3id)

    return md3vert_to_loop_map, loop_to_md3vert_map


def write_surface_shader(ctx, i, file):
    filename = ctx['mesh_shader_list'][i]
    # TODO: cut filename to quake path
    assert len(filename.encode('utf-8')) <= 64
    write_struct_to_file(file, '<64si', (filename.encode('utf-8'), i))


def write_surface_triangle(ctx, i, file):
    assert ctx['mesh'].polygons[i].loop_total == 3
    start = ctx['mesh'].polygons[i].loop_start
    a, c, b = (ctx['mesh_loop_to_md3vert'][j] for j in range(start, start + 3))  # swapped c/b
    write_struct_to_file(file, '<3i', (a, b, c))


def write_surface_ST(ctx, i, file):
    if ctx['mesh_uvmap_name'] is None:
        s, t = 0.0, 0.0
    else:
        loop_idx = ctx['mesh_md3vert_to_loop'][i]
        s, t = ctx['mesh'].uv_layers[ctx['mesh_uvmap_name']].data[loop_idx].uv
        t = 1.0 - t  # inverted t
    write_struct_to_file(file, '<ff', (s, t))


def interp(a, b, t):
    return (b - a) * t + a


def find_interval(vs, t):
    a, b = 0, len(vs) - 1
    if t < vs[a]:
        return None, a
    if t > vs[b]:
        return b, None
    while b - a > 1:
        c = (a + b) // 2
        if vs[c] > t:
            b = c
        else:
            a = c
    assert vs[a] <= t <= vs[b]
    return a, b


def _dict_remove(d, key):
    if key in d:
        del d[key]


def surface_start_frame(ctx, i, file):
    bpy.context.scene.frame_set(i)

    obj = bpy.context.scene.objects.active
    ctx['mesh'] = obj.to_mesh(bpy.context.scene, True, 'PREVIEW')
    ctx['mesh'].calc_normals_split()

    ctx['mesh_vco'][i] = ctx['mesh_vco'].get(i, [])

    _dict_remove(ctx, 'mesh_sk_rel')
    _dict_remove(ctx, 'mesh_sk_abs')
    # TODO: bones
    # TODO: object matrix

    shape_keys = ctx['mesh'].shape_keys
    if shape_keys is not None:
        kblocks = shape_keys.key_blocks
        if shape_keys.use_relative:
            ctx['mesh_sk_rel'] = [k.value for k in kblocks]
        else:
            e = shape_keys.eval_time / 100.0
            a, b = find_interval([k.frame for k in kblocks], e)
            if a is None:
                ctx['mesh_sk_abs'] = (b, b, 0.0)
            elif b is None:
                ctx['mesh_sk_abs'] = (a, a, 0.0)
            else:
                ctx['mesh_sk_abs'] = (a, b, (e - kblocks[a].frame) / (kblocks[b].frame - kblocks[a].frame))


def surface_end_frame(ctx, i, file):
    ctx['mesh'].free_normals_split()


def post_process_frame(ctx, i, file):
    center = mathutils.Vector((0.0, 0.0, 0.0))
    x1, x2, y1, y2, z1, z2 = [0.0] * 6
    first = True
    for co in ctx['mesh_vco'][i]:
        if first:
            x1, x2 = co.x, co.x
            y1, y2 = co.y, co.y
            z1, z2 = co.z, co.z
        else:
            x1, y1, z1 = min(co.x, x1), min(co.y, y1), min(co.z, z1)
            x2, y2, z2 = max(co.x, x2), max(co.y, y2), max(co.z, z2)
        first = False
        center += co
    center /= len(ctx['mesh_vco'][i])
    r = 0.0
    for co in ctx['mesh_vco'][i]:
        r = max(r, (co - center).length_squared)
    r = sqrt(r)

    resolve_delayed(ctx, file, 'frame{}_min'.format(i), (x1, y1, z1))
    resolve_delayed(ctx, file, 'frame{}_max'.format(i), (x2, y2, z2))
    resolve_delayed(ctx, file, 'frame{}_sphere'.format(i), (r,))


def get_evaluated_vertex_co(ctx, frame, i):
    co = ctx['mesh'].vertices[i].co.copy()

    if 'mesh_sk_rel' in ctx:
        bco = co.copy()
        for ki, k in enumerate(ctx['mesh'].shape_keys.key_blocks):
            co += (k.data[i].co - bco) * ctx['mesh_sk_rel'][ki]
    elif 'mesh_sk_abs' in ctx:
        kbs = ctx['mesh'].shape_keys.key_blocks
        a, b, t = ctx['mesh_sk_abs']
        co = interp(kbs[a].data[i].co, kbs[b].data[i].co, t)

    ctx['mesh_vco'][frame].append(co)
    return co


def encode_normal(n):
    x, y, z = n
    if x == 0 and y == 0:
        return bytes((0, 0)) if z > 0 else bytes((128, 0))
    lon = int(atan2(y, x) * 255 / (2 * pi)) & 255
    lat = int(acos(z) * 255 / (2 * pi)) & 255
    return bytes((lat, lon))


def write_surface_vert(ctx, frame, i, file):
    loop_id = ctx['mesh_md3vert_to_loop'][i]
    vert_id = ctx['mesh'].loops[loop_id].vertex_index
    x, y, z = [int(v * 64) for v in get_evaluated_vertex_co(ctx, frame, vert_id)]
    n = encode_normal(ctx['mesh'].loops[loop_id].normal)
    write_struct_to_file(file, '<hhh2s', (x, y, z, n))


def write_surface(ctx, i, file):
    surfaceOffset = file.tell()

    obj = bpy.context.scene.objects[ctx['surfNames'][i]]
    bpy.context.scene.objects.active = obj
    bpy.ops.object.modifier_add(type='TRIANGULATE')

    ctx['mesh'] = obj.to_mesh(bpy.context.scene, True, 'PREVIEW')
    ctx['mesh'].calc_normals_split()

    ctx['mesh_uvmap_name'], ctx['mesh_shader_list'] = gather_shader_info(ctx['mesh'])
    ctx['mesh_md3vert_to_loop'], ctx['mesh_loop_to_md3vert'] = gather_vertices(ctx['mesh'])
    ctx['mesh_vco'] = {}
    nShaders = len(ctx['mesh_shader_list'])
    nVerts = len(ctx['mesh_md3vert_to_loop'])
    nTris = len(ctx['mesh'].polygons)

    write_struct_to_file(file, '<4s64siiiii', (
        b'IDP3',
        obj.name.encode('utf-8'),
        0,  # flags, ignored
        ctx['modelFrames'],  # nFrames
        nShaders, nVerts, nTris
    ))
    write_delayed(ctx, file, 'surf_offTris', '<i', (0,))
    write_delayed(ctx, file, 'surf_offShaders', '<i', (0,))
    write_delayed(ctx, file, 'surf_offST', '<i', (0,))
    write_delayed(ctx, file, 'surf_offVerts', '<i', (0,))
    write_delayed(ctx, file, 'surf_offEnd', '<i', (0,))

    bpy.context.scene.frame_set(0)
    resolve_delayed(ctx, file, 'surf_offShaders', (file.tell() - surfaceOffset,))
    write_n_items(ctx, file, nShaders, write_surface_shader)
    resolve_delayed(ctx, file, 'surf_offTris', (file.tell() - surfaceOffset,))
    write_n_items(ctx, file, nTris, write_surface_triangle)
    resolve_delayed(ctx, file, 'surf_offST', (file.tell() - surfaceOffset,))
    write_n_items(ctx, file, nVerts, write_surface_ST)
    resolve_delayed(ctx, file, 'surf_offVerts', (file.tell() - surfaceOffset,))

    ctx['mesh'].free_normals_split()

    write_nm_items(ctx, file, ctx['modelFrames'], nVerts, write_surface_vert, surface_start_frame, surface_end_frame)
    resolve_delayed(ctx, file, 'surf_offEnd', (file.tell() - surfaceOffset,))

    bpy.ops.object.modifier_remove(modifier=obj.modifiers[-1].name)


def exportMD3(context, filename):
    with open(filename, 'wb') as file:
        nFrames = context.scene.frame_end - context.scene.frame_start + 1
        ctx = {
            'delayed': {},
            'context': context,
            'filename': filename,
            'modelFrames': nFrames,
            'surfNames': [],
            'tagNames': [],
        }
        for o in context.scene.objects:
            if o.type == 'MESH':
                ctx['surfNames'].append(o.name)
            elif o.type == 'EMPTY' and o.empty_draw_type == 'ARROWS':
                ctx['tagNames'].append(o.name)

        write_struct_to_file(file, '<4si64siiiii', (
            b'IDP3',  # magic
            15,  # version
            context.scene.name.encode('utf-8'),  # modelname
            0,  # flags, ignored
            nFrames,
            len(ctx['tagNames']),
            len(ctx['surfNames']),
            0,  # count of skins, ignored
        ))
        write_delayed(ctx, file, 'offFrames', '<i', (0,))
        write_delayed(ctx, file, 'offTags', '<i', (0,))
        write_delayed(ctx, file, 'offSurfaces', '<i', (0,))
        write_delayed(ctx, file, 'offEnd', '<i', (0,))

        resolve_delayed(ctx, file, 'offFrames', (file.tell(),))
        write_n_items(ctx, file, nFrames, write_frame)
        resolve_delayed(ctx, file, 'offTags', (file.tell(),))
        write_n_items(ctx, file, len(ctx['tagNames']), write_tag)
        resolve_delayed(ctx, file, 'offSurfaces', (file.tell(),))
        write_n_items(ctx, file, len(ctx['surfNames']), write_surface)
        resolve_delayed(ctx, file, 'offEnd', (file.tell(),))

        write_n_items(ctx, file, ctx['modelFrames'], post_process_frame)

        if ctx['delayed']:
            raise Exception('Not all delayed write resolved: {}'.format(ctx['delayed']))


class ExportMD3(bpy.types.Operator, ExportHelper):
    '''Export a Quake 3 Model MD3 file'''
    bl_idname = "export.md3"
    bl_label = 'Export MD3'
    filename_ext = ".md3"

    def execute(self, context):
        exportMD3(context, self.properties.filepath)
        return {'FINISHED'}

    def check(self, context):
        filepath = bpy.path.ensure_ext(self.filepath, '.md3')
        if filepath != self.filepath:
            self.filepath = filepath
            return True
        return False


def menu_func(self, context):
    self.layout.operator(ExportMD3.bl_idname, text="Quake 3 Model (.md3)")

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_export.append(menu_func)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_export.remove(menu_func)

if __name__ == "__main__":
    register()
