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
from .骨骼工具 import 骨骼与顶点组, 骨骼姿态操作, 骨骼编辑操作, MOD骨架替换
from .属性工具 import 顶点组, 形态键, UV贴图, 顶点色
from .其他工具 import 其他, 材质, 烘焙节点组

class XqfaPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    # 1. 定义一个辅助方法获取默认路径
    def get_default_texconv_path():
        # 获取当前文件（__init__.py）所在的目录
        addon_dir = os.path.dirname(__file__)
        # 拼接目标路径：插件目录/其他工具/texconv.exe
        default_path = os.path.join(addon_dir, "其他工具", "texconv.exe")
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
    骨骼与顶点组.register()
    骨骼姿态操作.register()
    骨骼编辑操作.register()
    MOD骨架替换.register()
    顶点组.register()
    形态键.register()
    UV贴图.register()
    顶点色.register()
    其他.register()
    材质.register()
    烘焙节点组.register()

# 注销插件
def unregister():
    bpy.utils.unregister_class(XqfaPreferences)
    panel.unregister()
    骨骼与顶点组.unregister()
    骨骼姿态操作.unregister()
    骨骼编辑操作.unregister()
    MOD骨架替换.unregister()
    顶点组.unregister()
    形态键.unregister()
    UV贴图.unregister()
    顶点色.unregister()
    其他.unregister()
    材质.unregister()
    烘焙节点组.unregister()


if __name__ == "__main__":
    register()

