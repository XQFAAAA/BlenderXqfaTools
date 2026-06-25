# type: ignore
import bpy
import os
import csv, json
from bpy_extras.io_utils import ImportHelper

class ObjType(bpy.types.Operator):
    def is_mesh(scene, obj):
        return obj.type == "MESH"
    
    def is_armature(scene, obj):
        return obj.type == "ARMATURE"

class O_ImportCSV(bpy.types.Operator, ImportHelper):
    bl_idname = "xqfa.csv_import"
    bl_label = "导入CSV"
    bl_description = ""
    filename_ext = ".csv"
    filter_glob: bpy.props.StringProperty(
        default="*.csv",
        options={'HIDDEN'},
    )

    def execute(self, context):
        csv_file = self.filepath

        if not csv_file or not os.path.exists(csv_file):
            self.report({'ERROR'}, "请选择有效的CSV文件")
            return {'CANCELLED'}

        # 尝试的编码顺序
        encodings = ['utf-8', 'gbk', 'utf-16']
        
        for encoding in encodings:
            try:
                with open(csv_file, 'r', newline='', encoding=encoding) as file:
                    reader = csv.reader(file)
                    csv_data = list(reader)
                    # 存储为 JSON 字符串
                    context.scene["xbone_csv_data"] = json.dumps(csv_data)
                
                self.report({'INFO'}, f"CSV文件已导入({encoding}): {csv_file}")
                return {'FINISHED'}
            except UnicodeDecodeError:
                continue
            except Exception as e:
                self.report({'ERROR'}, f"导入CSV文件时出现错误: {e}")
                return {'CANCELLED'}
        
        self.report({'ERROR'}, "无法解码CSV文件，请尝试转换为UTF-8编码")
        return {'CANCELLED'}


class O_BoneSimpleMapping(bpy.types.Operator):
    bl_idname = "xqfa.simple_mapping"
    bl_label = "简化骨骼"
    bl_description = "根据CSV映射表保留主骨骼、处理合并逻辑并清理多余骨骼"

    def execute(self, context):
        scene = context.scene
        # 1. 安全检查
        if not scene.xbone_csv_data:
            self.report({'ERROR'}, "请先导入CSV文件")
            return {'CANCELLED'}
        
        target_obj = scene.simple_source_armature
        if not target_obj or target_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "目标骨架对象无效")
            return {'CANCELLED'}

        try:
            csv_data = json.loads(scene.xbone_csv_data)
        except Exception as e:
            self.report({'ERROR'}, f"解析CSV数据失败: {e}")
            return {'CANCELLED'}

        # 2. 提取配置
        cols = {
            'main': scene.simple_main_column,
            'save': scene.simple_save_column,
            'active': scene.simple_active_column,
            'to_active': scene.simple_toactive_column
        }
        
        bone_main = set()
        bone_save = set()
        bone_mapping = {}

        # 3. 单次遍历解析 CSV 数据 (优化点：将之前的 3 个循环合并为一个)
        for row in csv_data[1:]:
            row_len = len(row)
            
            # 提取主骨骼和保留骨骼
            for key, attr in [('main', bone_main), ('save', bone_save)]:
                idx = cols[key]
                if row_len > idx:
                    val = str(row[idx])
                    if val and val != "None":
                        attr.add(val)

            # 提取映射关系
            m_idx, t_idx = cols['active'], cols['to_active']
            if row_len > max(m_idx, t_idx):
                key_bone, val_bone = str(row[t_idx]), str(row[m_idx])
                if all([key_bone, val_bone, key_bone != "None", val_bone != "None"]):
                    bone_mapping[key_bone] = val_bone

        # 4. 骨骼集合处理函数 (提高代码重用性)
        def assign_bones_to_collection(armature, bone_names, coll_name, palette):
            if not bone_names: return
            coll = armature.data.collections.get(coll_name) or armature.data.collections.new(coll_name)
            for name in bone_names:
                p_bone = armature.pose.bones.get(name)
                if p_bone:
                    coll.assign(p_bone.bone)
                    p_bone.bone.color.palette = palette

        # 进入姿态模式
        bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.objects.active = target_obj
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.reveal()

        # 5. 分配集合与颜色 (优化点：减少模式切换，批量处理)
        assign_bones_to_collection(target_obj, bone_main, "主骨骼", 'THEME02')
        assign_bones_to_collection(target_obj, bone_save, "保留骨骼", 'THEME09')

        # 6. 执行特定合并 (保持原有逻辑，但优化选择操作)
        # 注意：此处仍需调用你自定义的 merge_to_active 算子
        for to_active, active in bone_mapping.items():
            if to_active in target_obj.pose.bones and active in target_obj.pose.bones:
                bpy.ops.pose.select_all(action='DESELECT')
                target_obj.data.bones[to_active].select = True
                target_obj.data.bones.active = target_obj.data.bones[active]
                bpy.ops.xqfa.merge_to_active()

        # 7. 剩余骨骼合并至父级
        # 优化点：使用集合运算快速找出需要处理的骨骼
        all_pose_bones = set(target_obj.pose.bones.keys())
        keep_bones = bone_main.union(bone_save)
        bones_to_parent = all_pose_bones - keep_bones

        if bones_to_parent:
            bpy.ops.pose.select_all(action='DESELECT')
            for b_name in bones_to_parent:
                if b_name in target_obj.data.bones:
                    target_obj.data.bones[b_name].select = True
            
            # 调用自定义合并至父级算子
            bpy.ops.xqfa.merge_to_parent()
            
            # 8. 删除骨骼
            bpy.ops.object.mode_set(mode='EDIT')
            # 此时选中的依然是 bones_to_parent
            bpy.ops.armature.delete()
            bpy.ops.object.mode_set(mode='POSE')

        # 9. 清理工作
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.pose.constraints_clear()
        
        self.report({'INFO'}, "简化骨骼操作完成")
        return {'FINISHED'}  
    
class O_only_BoneRenameMapping(bpy.types.Operator):
    bl_idname = "xqfa.only_rename_mapping"
    bl_label = "重命名"
    bl_description = "将源骨架骨骼按csv对应, 重命名"

    def execute(self, context):
        if context.scene.xbone_csv_data == "":
            self.report({'ERROR'}, "似乎没有导入csv")
            return {'FINISHED'}
        try:
            TargetArmature = bpy.data.objects.get(context.scene.rename_armature.name)
        except:
            self.report({'ERROR'}, "似乎没有选择对象") 
            return {'FINISHED'}
        
        csv_data = json.loads(context.scene["xbone_csv_data"])
        current_skel_column = context.scene.current_skel_column
        change_skel_column = context.scene.change_skel_column
        bone_mapping = {}
        # 读取CSV文件中的数据
        for row in csv_data[1:]:  # 跳过标题行
            if len(row) <= max(current_skel_column, change_skel_column):
                continue  # 确保行有足够的列
            key = str(row[current_skel_column])
            value = str(row[change_skel_column])
            if (key == "None") or (value == "None"):
                continue
            bone_mapping[key] = value

        # 姿态模式重命名
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = TargetArmature
        bpy.ops.object.mode_set(mode='POSE')
        rename_count = 0
        for current_bone_name, change_bone_name in bone_mapping.items():
            try:
                TargetArmature.data.bones[current_bone_name].name = change_bone_name
                rename_count += 1
            except:
                print(f"{current_bone_name}不存在")

        # 生成映射记录到 xqfa_vertex_group_mappings
        scene = context.scene
        if hasattr(scene, 'xqfa_vertex_group_mappings'):
            mappings = scene.xqfa_vertex_group_mappings
            item = mappings.add()
            item.label = f"重命名映射 {len(mappings)}"
            item.expanded = False
            for current_bone_name, change_bone_name in bone_mapping.items():
                p = item.pairs.add()
                p.left_name = current_bone_name
                p.right_name = change_bone_name
                p.similarity = ""

        self.report({'INFO'}, f"已重命名 {rename_count} 个骨骼")
        return {'FINISHED'}

class P_BoneMapping(bpy.types.Panel):
    bl_label = "骨架"
    bl_idname = "X_PT_BoneMapping"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'
    bl_options = {'DEFAULT_CLOSED'} #默认折叠

    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了此子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'BoneTools'
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.operator(O_ImportCSV.bl_idname, icon="IMPORT")
        # 选择骨架
        box.prop(context.scene, "simple_source_armature", text="目标骨架", icon="ARMATURE_DATA")
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(context.scene, "simple_main_column")
        row.prop(context.scene, "simple_save_column")
        row = col.row(align=True)
        row.prop(context.scene, "simple_active_column")
        row.prop(context.scene, "simple_toactive_column")
        # 添加按钮
        col.operator(O_BoneSimpleMapping.bl_idname, icon="PLAY")


        box = layout.box()
        # 批量重命名 选择目标骨架
        col = box.column(align=True)
        col.prop(context.scene, "rename_armature", text="目标骨架", icon="ARMATURE_DATA")
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(context.scene, "current_skel_column")
        row.prop(context.scene, "change_skel_column")
        # 添加按钮
        col.operator(O_only_BoneRenameMapping.bl_idname, icon="PLAY")

        



def register():
    bpy.utils.register_class(O_ImportCSV)
    bpy.utils.register_class(O_BoneSimpleMapping)
    bpy.utils.register_class(O_only_BoneRenameMapping)
    bpy.utils.register_class(P_BoneMapping)
    ########################## Divider ##########################
    bpy.types.Scene.xbone_csv_data = bpy.props.StringProperty(
        name="CSV Data",
        description="Stores imported CSV data as JSON",
        default=""
    )

    bpy.types.Scene.simple_source_armature = bpy.props.PointerProperty(
        description="选择将被作用的骨架",
        type=bpy.types.Object, 
        poll=ObjType.is_armature
        )
    bpy.types.Scene.rename_armature = bpy.props.PointerProperty(
        description="选择将被作用的骨架",
        type=bpy.types.Object, 
        poll=ObjType.is_armature
        )
    ########################## Divider ##########################
    bpy.types.Scene.simple_main_column = bpy.props.IntProperty(
        name="主骨骼",
        description="主要骨骼的列索引",
        default=1,
        min=0,
    )
    bpy.types.Scene.simple_save_column = bpy.props.IntProperty(
        name="保留骨",
        description="可以后续调整物理的骨骼列索引",
        default=2,
        min=0,
    )
    bpy.types.Scene.simple_active_column = bpy.props.IntProperty(
        name="指定骨",
        description="",
        default=3,
        min=0,
    )
    bpy.types.Scene.simple_toactive_column = bpy.props.IntProperty(
        name="合并到指定",
        description="会被合并至指定的骨骼",
        default=4,
        min=0,
    )
    ########################## Divider ##########################
    bpy.types.Scene.current_skel_column = bpy.props.IntProperty(
        name="源名称",
        description="源名称改为目标名称\n0是第1列",
        default=1,
        min=0,
    )
    bpy.types.Scene.change_skel_column = bpy.props.IntProperty(
        name="目标名称",
        description="源名称改为目标名称\n0是第1列",
        default=0,
        min=0,
    )    

def unregister():
    bpy.utils.unregister_class(O_ImportCSV)
    bpy.utils.unregister_class(O_BoneSimpleMapping)
    bpy.utils.unregister_class(O_only_BoneRenameMapping)    
    bpy.utils.unregister_class(P_BoneMapping)

    del bpy.types.Scene.xbone_csv_data

    del bpy.types.Scene.simple_source_armature
    del bpy.types.Scene.rename_armature
    

    del bpy.types.Scene.simple_main_column
    del bpy.types.Scene.simple_save_column
    del bpy.types.Scene.simple_toactive_column
    del bpy.types.Scene.simple_active_column

    del bpy.types.Scene.current_skel_column
    del bpy.types.Scene.change_skel_column

