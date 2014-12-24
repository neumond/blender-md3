# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


# grouping to surfaces must done by UV maps also, not only normals
# TODO: merge surfaces with same uv maps and texture
# TODO: check bounding sphere calculation


import bpy
import mathutils
import struct
from math import atan2, acos, pi, sqrt
import re


nums = re.compile(r'\.\d{3}$')
def prepare_name(name):
    if nums.findall(name):
        return name[:-4]  # cut off blender's .001 .002 etc
    return name


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


def write_tag(ctx, frame, i, file):
    tag = bpy.context.scene.objects[ctx['tagNames'][i]]
    origin = tuple(tag.location)
    ox = tuple(tag.matrix_basis[0][:3])
    oy = tuple(tag.matrix_basis[1][:3])
    oz = tuple(tag.matrix_basis[2][:3])
    write_struct_to_file(file, '<64s12f', (prepare_name(tag.name).encode('utf-8'),) + origin + ox + oy + oz)


def tag_start_frame(ctx, i, file):
    bpy.context.scene.frame_set(bpy.context.scene.frame_start + i)


def tag_end_frame(ctx, i, file):
    pass


def gather_shader_info(mesh):
    'Returning uvmap name, texture name list'
    uv_maps = {}
    for material in mesh.materials:
        for texture_slot in material.texture_slots:
            if texture_slot is None or not texture_slot.use or not texture_slot.uv_layer\
                or texture_slot.texture_coords != 'UV' or not texture_slot.texture\
                or texture_slot.texture.type != 'IMAGE':
                continue
            uv_map_name = texture_slot.uv_layer
            if uv_map_name not in uv_maps:
                uv_maps[uv_map_name] = []
            # one UV map can be used by many textures
            uv_maps[uv_map_name].append(prepare_name(texture_slot.texture.name))
    uv_maps = [(k, v) for k, v in uv_maps.items()]
    if len(uv_maps) <= 0:
        print('Warning: No UV maps found, zero filling will be used')
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
    texname = prepare_name(ctx['mesh_shader_list'][i]).encode('utf-8')
    if len(texname) > 64:
        print('Warning: name of texture is too long: {}'.format(texname.decode('utf-8')))
        texname = texname[:64]
    write_struct_to_file(file, '<64si', (texname, i))


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
    bpy.context.scene.frame_set(bpy.context.scene.frame_start + i)

    obj = bpy.context.scene.objects.active
    ctx['mesh_matrix'] = obj.matrix_world
    ctx['mesh'] = obj.to_mesh(bpy.context.scene, True, 'PREVIEW')
    ctx['mesh'].calc_normals_split()

    ctx['mesh_vco'][i] = ctx['mesh_vco'].get(i, [])

    _dict_remove(ctx, 'mesh_sk_rel')
    _dict_remove(ctx, 'mesh_sk_abs')

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

    co = ctx['mesh_matrix'] * co
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
    x, y, z = [int(v * 64.0) for v in get_evaluated_vertex_co(ctx, frame, vert_id)]
    n = encode_normal(ctx['mesh'].loops[loop_id].normal)
    write_struct_to_file(file, '<hhh2s', (x, y, z, n))


def write_surface(ctx, i, file):
    surfaceOffset = file.tell()

    obj = bpy.context.scene.objects[ctx['surfNames'][i]]
    bpy.context.scene.objects.active = obj
    bpy.ops.object.modifier_add(type='TRIANGULATE')  # no 4-gons or n-gons
    ctx['mesh'] = obj.to_mesh(bpy.context.scene, True, 'PREVIEW')

    ctx['mesh'].calc_normals_split()

    ctx['mesh_uvmap_name'], ctx['mesh_shader_list'] = gather_shader_info(ctx['mesh'])
    ctx['mesh_md3vert_to_loop'], ctx['mesh_loop_to_md3vert'] = gather_vertices(ctx['mesh'])
    ctx['mesh_vco'] = {}
    nShaders = len(ctx['mesh_shader_list'])
    nVerts = len(ctx['mesh_md3vert_to_loop'])
    nTris = len(ctx['mesh'].polygons)
    if nShaders > 256:
        print('Warning: too many textures')
    if nVerts > 4096:
        print('Warning: too many vertices')
    if nTris > 8192:
        print('Warning: too many triangles')

    write_struct_to_file(file, '<4s64siiiii', (
        b'IDP3',
        prepare_name(obj.name).encode('utf-8'),
        0,  # flags, ignored
        ctx['modelFrames'],  # nFrames
        nShaders, nVerts, nTris
    ))
    write_delayed(ctx, file, 'surf_offTris', '<i', (0,))
    write_delayed(ctx, file, 'surf_offShaders', '<i', (0,))
    write_delayed(ctx, file, 'surf_offST', '<i', (0,))
    write_delayed(ctx, file, 'surf_offVerts', '<i', (0,))
    write_delayed(ctx, file, 'surf_offEnd', '<i', (0,))

    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
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

    # release here, to_mesh used for every frame
    bpy.ops.object.modifier_remove(modifier=obj.modifiers[-1].name)

    print('Surface {}: nVerts={} nTris={} nShaders={}'.format(i, nVerts, nTris, nShaders))


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
            prepare_name(context.scene.name).encode('utf-8'),  # modelname
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
        write_nm_items(ctx, file, nFrames, len(ctx['tagNames']), write_tag, tag_start_frame, tag_end_frame)
        resolve_delayed(ctx, file, 'offSurfaces', (file.tell(),))
        write_n_items(ctx, file, len(ctx['surfNames']), write_surface)
        resolve_delayed(ctx, file, 'offEnd', (file.tell(),))

        write_n_items(ctx, file, ctx['modelFrames'], post_process_frame)

        if ctx['delayed']:
            raise Exception('Not all delayed write resolved: {}'.format(ctx['delayed']))

        print('nFrames={} nSurfaces={}'.format(nFrames, len(ctx['surfNames'])))
