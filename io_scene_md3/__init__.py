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


bl_info = {
    "name": "Quake 3 Model (.md3)",
    "author": "Vitaly Verhovodov",
    "version": (0, 1, 0),
    "blender": (2, 6, 9),
    "location": "File > Import-Export > Quake 3 Model",
    "description": "Quake 3 Model format (.md3)",
    "warning": "",
    "wiki_url": "http://wiki.blender.org/index.php/Extensions:2.6/Py/Scripts/Import-Export/MD3",
    "tracker_url": "https://github.com/neumond/blender-md3/issues",
    "category": "Import-Export"}


import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper


class ImportMD3(bpy.types.Operator, ImportHelper):
    '''Import a Quake 3 Model MD3 file'''
    bl_idname = "import_scene.md3"
    bl_label = 'Import MD3'
    filename_ext = ".md3"
    filter_glob = StringProperty(default="*.md3", options={'HIDDEN'})

    def execute(self, context):
        from . import import_md3
        import_md3.importMD3(context, self.properties.filepath)
        return {'FINISHED'}


class ExportMD3(bpy.types.Operator, ExportHelper):
    '''Export a Quake 3 Model MD3 file'''
    bl_idname = "export_scene.md3"
    bl_label = 'Export MD3'
    filename_ext = ".md3"
    filter_glob = StringProperty(default="*.md3", options={'HIDDEN'})

    def execute(self, context):
        from . import export_md3
        export_md3.exportMD3(context, self.properties.filepath)
        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(ImportMD3.bl_idname, text="Quake 3 Model (.md3)")

def menu_func_export(self, context):
    self.layout.operator(ExportMD3.bl_idname, text="Quake 3 Model (.md3)")


def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_import.append(menu_func_import)
    bpy.types.INFO_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()
