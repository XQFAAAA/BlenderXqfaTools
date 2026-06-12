# type: ignore
import bpy
import os
bl_info = {
    "name" : "XqfaTools",
    "author" : "xqfa",
    "description" : "",
    "blender" : (4, 5, 0),
    "version" : (2, 0, 0),
    "location" : "",
    "warning" : "",
    "category" : "Generic"
}

########################## Divider ##########################
from . import panel
from .bone_tools import bone_and_vertex_groups, bone_pose, bone_edit, mod_armature_replace
from .attribute_tools import vertex_groups, shapekey, uv, vertex_colors, extra_object_info
from .other_tools import misc
from .material_tools import material, bake_node_groups, material_batch, material_snapshot

class XqfaPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    # 1. 定义一个辅助方法获取默认路径
    def get_default_texconv_path():
        # 获取当前文件（__init__.py）所在的目录
        addon_dir = os.path.dirname(__file__)
        # 拼接目标路径：插件目录/other_tools/texconv.exe
        default_path = os.path.join(addon_dir, "other_tools", "texconv.exe")
        return default_path

    # 2. 将默认值设为计算出的路径
    texconv_path: bpy.props.StringProperty(
        name="texconv.exe 路径",
        subtype='FILE_PATH',
        description="用于转换 DDS 格式的工具路径",
        default=get_default_texconv_path()
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "texconv_path")


# 注册插件
def register():
    bpy.utils.register_class(XqfaPreferences)
    panel.register()
    bone_and_vertex_groups.register()
    bone_pose.register()
    bone_edit.register()
    mod_armature_replace.register()
    vertex_groups.register()
    shapekey.register()
    uv.register()
    vertex_colors.register()
    extra_object_info.register()
    misc.register()
    material.register()
    material_snapshot.register()
    material_batch.register()
    bake_node_groups.register()

# 注销插件
def unregister():
    bpy.utils.unregister_class(XqfaPreferences)
    panel.unregister()
    bone_and_vertex_groups.unregister()
    bone_pose.unregister()
    bone_edit.unregister()
    mod_armature_replace.unregister()
    vertex_groups.unregister()
    shapekey.unregister()
    uv.unregister()
    vertex_colors.unregister()
    extra_object_info.unregister()
    misc.unregister()
    material.unregister()
    material_snapshot.unregister()
    material_batch.unregister()
    bake_node_groups.unregister()


if __name__ == "__main__":
    register()

