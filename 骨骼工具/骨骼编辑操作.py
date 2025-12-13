# type: ignore
import bpy 
import math
from mathutils import Euler, Matrix, Vector, Quaternion

########################## Divider ##########################

class PG_BoneEditWorldProps(bpy.types.PropertyGroup):
    #注册切换矩阵显示的布尔值
    edit_matrix: bpy.props.BoolProperty(
        name="矩阵", 
        default=False
    )
    #编辑模式
    def get_edit_position(self):
        active_bone = bpy.context.active_bone
        if active_bone:
            return active_bone.matrix.translation
        return (0.0, 0.0, 0.0)
    def set_edit_position(self, value):
        active_bone = bpy.context.active_bone
        if active_bone:
            new_matrix = active_bone.matrix
            new_matrix.translation = value
            active_bone.matrix = new_matrix

    def get_edit_euler_rotation(self):
        active_bone = bpy.context.active_bone
        if active_bone:
            return active_bone.matrix.to_euler()
        return (0.0, 0.0, 0.0)
    def set_edit_euler_rotation(self, value):
        active_bone = bpy.context.active_bone
        if active_bone:
            new_rotation = Euler(value, 'XYZ')
            new_matrix = new_rotation.to_matrix().to_4x4()
            new_matrix.translation = active_bone.matrix.translation
            active_bone.matrix = new_matrix
            
    def get_edit_quaternion_rotation(self):
        active_bone = bpy.context.active_bone
        if active_bone:
            return active_bone.matrix.to_quaternion()
        return Quaternion()
    def set_edit_quaternion_rotation(self, value):
        active_bone = bpy.context.active_bone
        if active_bone:
            new_quat = Quaternion(value)
            new_matrix = new_quat.to_matrix().to_4x4()
            new_matrix.translation = active_bone.matrix.translation
            active_bone.matrix = new_matrix
                        
    edit_position: bpy.props.FloatVectorProperty(
        name="Edit Position",
        get=get_edit_position,
        set=set_edit_position,
        subtype='TRANSLATION',
        unit='LENGTH',
        size=3,
        precision=3,
    )
    
    edit_euler_rotation: bpy.props.FloatVectorProperty(
        name="Edit Euler Rotation",
        get=get_edit_euler_rotation,
        set=set_edit_euler_rotation,
        subtype='EULER',
        unit='ROTATION',
        size=3,
        precision=3,
    )
    
    edit_quaternion_rotation: bpy.props.FloatVectorProperty(
        name="Edit Quaternion Rotation",
        get=get_edit_quaternion_rotation,
        set=set_edit_quaternion_rotation,
        subtype='QUATERNION',
        unit='NONE',
        size=4,  # 四元数具有四个分量
        precision=3,
    ) 

class O_BoneEditYUp(bpy.types.Operator):
    bl_idname = "xbone.edit_y_up"
    bl_label = "90 0 0"
    bl_description = "选中骨骼Y轴向上右手坐标系, 请先应用骨架旋转"

    def execute(self, context):

        obj = context.active_object
        if obj and obj.type == 'ARMATURE': # 检查对象是否为骨骼对象
            if context.selected_bones: #有选择骨骼

                order_selected_bones = []
                for bone1 in obj.data.bones: #遍历骨架中的每一根骨骼，若被选中则加入list, 保证顺序正确
                    for bone2 in context.selected_bones:
                        if bone1.name == bone2.name :
                            order_selected_bones.append(bone2)

                for bone in order_selected_bones:
                    new_rotation = Euler((math.radians(90), math.radians(0), math.radians(0)), 'XYZ')
                    new_matrix = new_rotation.to_matrix().to_4x4()
                    new_matrix.translation = bone.matrix.translation
                    bone.matrix = new_matrix
                    # 刷新
                    bpy.context.view_layer.update()
        return {"FINISHED"}
    
class O_BoneEditZUp(bpy.types.Operator):
    bl_idname = "xbone.edit_z_up"
    bl_label = "0 0 0"
    bl_description = "选中骨骼Y轴向上右手坐标系, 请先应用骨架旋转"

    def execute(self, context):

        obj = context.active_object
        if obj and obj.type == 'ARMATURE': # 检查对象是否为骨骼对象
            if context.selected_bones: #有选择骨骼

                order_selected_bones = []
                for bone1 in obj.data.bones: #遍历骨架中的每一根骨骼，若被选中则加入list, 保证顺序正确
                    for bone2 in context.selected_bones:
                        if bone1.name == bone2.name :
                            order_selected_bones.append(bone2)

                for bone in order_selected_bones:
                    new_rotation = Euler((math.radians(0), math.radians(0), math.radians(0)), 'XYZ')
                    new_matrix = new_rotation.to_matrix().to_4x4()
                    new_matrix.translation = bone.matrix.translation
                    bone.matrix = new_matrix
                    # 刷新
                    bpy.context.view_layer.update()
        return {"FINISHED"}

class O_BoneEditUpRight(bpy.types.Operator):
    bl_idname = "xbone.edit_upright"
    bl_label = "自动摆正"
    bl_description = "选择当前朝向相近的正交方向 by 夜曲"

    def execute(self, context):

        target_angles = [-180, -90, 0, 90, 180]
        obj = context.active_object
        if obj and obj.type == 'ARMATURE': # 检查对象是否为骨骼对象
            if context.selected_bones: #有选择骨骼

                order_selected_bones = []
                for bone1 in obj.data.bones: #遍历骨架中的每一根骨骼，若被选中则加入list, 保证顺序正确
                    for bone2 in context.selected_bones:
                        if bone1.name == bone2.name :
                            order_selected_bones.append(bone2)

                for bone in order_selected_bones:
                    angles_radians = bone.matrix.to_euler()
                    angles_degrees = (math.degrees(angles_radians.x),math.degrees(angles_radians.y),math.degrees(angles_radians.z))

                    x, y, z = angles_degrees
                    x = min(target_angles, key=lambda n: abs(n - x))
                    y = min(target_angles, key=lambda n: abs(n - y))
                    z = min(target_angles, key=lambda n: abs(n - z))
                    
                    new_rotation = Euler((math.radians(x), math.radians(y), math.radians(z)), 'XYZ')
                    new_matrix = new_rotation.to_matrix().to_4x4()
                    new_matrix.translation = bone.matrix.translation
                    bone.matrix = new_matrix
                    # 刷新
                    bpy.context.view_layer.update()

        return {"FINISHED"}

class O_BoneEditX90(bpy.types.Operator):
    bl_idname = "xbone.edit_x90"
    bl_label = "绕x旋转90°"
    bl_description = ""

    def execute(self, context):

        obj = context.active_object
        if obj and obj.type == 'ARMATURE': # 检查对象是否为骨骼对象
            if context.selected_bones: #有选择骨骼

                order_selected_bones = []
                for bone1 in obj.data.bones: #遍历骨架中的每一根骨骼，若被选中则加入list, 保证顺序正确
                    for bone2 in context.selected_bones:
                        if bone1.name == bone2.name :
                            order_selected_bones.append(bone2)

                for bone in order_selected_bones:
                    # 获取骨骼的原始矩阵
                    original_matrix = bone.matrix.copy()
                    # 变换矩阵
                    new_rotation = Euler((math.radians(90), math.radians(0), math.radians(0)), 'XYZ')
                    rotation_matrix = new_rotation.to_matrix().to_4x4()
                    # 相乘
                    new_matrix = rotation_matrix @ original_matrix
                    # 使用原坐标
                    new_matrix.translation = bone.matrix.translation
                    # 赋值
                    bone.matrix = new_matrix
                    # 刷新
                    bpy.context.view_layer.update()

        return {"FINISHED"}

class O_BoneEditY90(bpy.types.Operator):
    bl_idname = "xbone.edit_y90"
    bl_label = "绕y旋转90°"
    bl_description = ""

    def execute(self, context):

        obj = context.active_object
        if obj and obj.type == 'ARMATURE': # 检查对象是否为骨骼对象
            if context.selected_bones: #有选择骨骼

                order_selected_bones = []
                for bone1 in obj.data.bones: #遍历骨架中的每一根骨骼，若被选中则加入list, 保证顺序正确
                    for bone2 in context.selected_bones:
                        if bone1.name == bone2.name :
                            order_selected_bones.append(bone2)

                for bone in order_selected_bones:
                    original_matrix = bone.matrix.copy()
                    new_rotation = Euler((math.radians(0), math.radians(90), math.radians(0)), 'XYZ')
                    rotation_matrix = new_rotation.to_matrix().to_4x4()
                    new_matrix = rotation_matrix @ original_matrix
                    new_matrix.translation = bone.matrix.translation
                    bone.matrix = new_matrix
                    bpy.context.view_layer.update()

        return {"FINISHED"}

class O_BoneEditZ90(bpy.types.Operator):
    bl_idname = "xbone.edit_z90"
    bl_label = "绕z旋转90°"
    bl_description = ""

    def execute(self, context):

        obj = context.active_object
        if obj and obj.type == 'ARMATURE': # 检查对象是否为骨骼对象
            if context.selected_bones: #有选择骨骼

                order_selected_bones = []
                for bone1 in obj.data.bones: #遍历骨架中的每一根骨骼，若被选中则加入list, 保证顺序正确
                    for bone2 in context.selected_bones:
                        if bone1.name == bone2.name :
                            order_selected_bones.append(bone2)

                for bone in order_selected_bones:
                    original_matrix = bone.matrix.copy()
                    new_rotation = Euler((math.radians(0), math.radians(0), math.radians(90)), 'XYZ')
                    rotation_matrix = new_rotation.to_matrix().to_4x4()
                    new_matrix = rotation_matrix @ original_matrix
                    new_matrix.translation = bone.matrix.translation
                    bone.matrix = new_matrix
                    bpy.context.view_layer.update()

        return {"FINISHED"}

########################## Divider ##########################

class O_BoneConnect(bpy.types.Operator):
    bl_idname = "xbone.connect"
    bl_label = "选中取消相连"
    bl_description = ""

    def execute(self, context):

        obj = context.active_object
        if obj and obj.type == 'ARMATURE': # 检查对象是否为骨骼对象
            if context.selected_bones: #编辑模式有选择骨骼
                for bone in context.selected_bones:
                    bone.use_connect = False

        return {"FINISHED"}

class O_BoneAllConnect(bpy.types.Operator):
    bl_idname = "xbone.all_connect"
    bl_label = "所有取消相连"
    bl_description = ""

    def execute(self, context):

        obj = context.active_object
        if obj and obj.type == 'ARMATURE': # 检查对象是否为骨骼对象
            save_mode = context.mode
            if save_mode == "EDIT_ARMATURE": save_mode = "EDIT"
            bpy.ops.object.mode_set(mode = 'EDIT') #进入编辑模式
            bpy.ops.armature.select_all(action='SELECT') #取消选择
            for bone in context.selected_bones:
                bone.use_connect = False
            bpy.ops.armature.select_all(action='DESELECT') #取消选择
            bpy.ops.object.mode_set(mode = save_mode) #返回之前的模式
        else:
            print("对象不是骨架")
        return {"FINISHED"}
         

########################## Divider ##########################

class O_BoneMoveTailToChild(bpy.types.Operator):
    bl_idname = "xbone.move_tail_to_child"
    bl_label = "选中骨骼尾部-->子级平均/父级矩阵"
    bl_description = "将选中骨骼的尾部移动到其选中子级头部的平均位置；或若无子级，使用父级矩阵但不移动头部"

    def execute(self, context):
        # 确保在编辑模式下
        if context.mode != 'EDIT_ARMATURE':
            self.report({'WARNING'}, "必须在骨骼编辑模式下运行此操作")
            return {'CANCELLED'}
        
        # 获取骨架对象
        armature_obj = context.object
        if not armature_obj or armature_obj.type != 'ARMATURE':
            self.report({'WARNING'}, "未选择骨架对象")
            return {'CANCELLED'}
        
        # 根据骨架名称生成1-9的数字
        def get_theme_number_from_name(name):
            # 计算名称的简单哈希值
            hash_value = 0
            for char in name:
                # 使用一个相对较小的乘数来避免溢出，并保持简单的分布
                hash_value = (hash_value * 31 + ord(char)) % 10000 
            return (hash_value % 9) + 1  # 确保在1-9范围内
        
        theme_number = get_theme_number_from_name(armature_obj.name)
        theme_name = f"THEME0{theme_number}"
        
        # 获取当前选中的骨骼
        selected_bones = context.selected_editable_bones
        
        if not selected_bones:
            self.report({'WARNING'}, "没有选中任何骨骼")
            return {'CANCELLED'}
        
        # 创建选中骨骼名称的集合，用于快速查找
        selected_bone_names = {bone.name for bone in selected_bones}
        
        # 获取骨架的世界变换矩阵
        armature_matrix = armature_obj.matrix_world
        armature_matrix_inv = armature_matrix.inverted()
        
        # 记录成功操作的骨骼
        moved_bones = []
        rotated_bones = []
        
        # 遍历所有选中的骨骼
        for bone in selected_bones:
            # --- 逻辑 1: 移动尾部到子级平均头部位置 ---
            children = bone.children
            
            # 找到在选中范围内的子级
            selected_children = [child for child in children if child.name in selected_bone_names]
            
            if selected_children:
                # 计算所有选中子级头部的世界坐标系平均位置
                head_sum_world = Vector((0.0, 0.0, 0.0))
                for child in selected_children:
                    head_sum_world += armature_matrix @ child.head
                
                # 平均世界位置
                avg_child_head_world = head_sum_world / len(selected_children)
                
                # 当前骨骼尾部的世界坐标
                bone_tail_world = armature_matrix @ bone.tail
                
                # 计算在世界坐标系中的移动向量
                move_vector_world = avg_child_head_world - bone_tail_world
                
                # 执行移动操作（只移动尾部）
                
                # 1. 恢复选择状态，确保只有当前骨骼的尾部被选中
                bpy.ops.armature.select_all(action='DESELECT')
                bone.select = True
                bone.select_head = False
                bone.select_tail = True
                
                # 2. 设置当前骨骼为活动骨骼
                context.view_layer.objects.active = armature_obj
                armature_obj.data.edit_bones.active = bone
                
                # 3. 使用transform.translate来移动尾部（在世界坐标系中）
                bpy.ops.transform.translate(value=move_vector_world)
                
                moved_bones.append(bone)

            # --- 逻辑 2: 无子级时，继承父级的矩阵但不移动头部 ---
            elif not children and bone.parent:
                parent_bone = bone.parent
                
                # 获取父级骨骼的局部矩阵
                parent_matrix = parent_bone.matrix
                
                # 创建一个新的矩阵，继承父级的旋转和缩放，但保持当前骨骼的头部位置
                new_bone_matrix = parent_matrix.to_3x3().to_4x4() # 只取旋转和缩放部分
                
                # 保持当前的头部位置
                # 当前头部在骨架坐标系下的坐标
                bone_head_local = bone.head
                
                # 将头部坐标赋值给新矩阵的平移分量
                new_bone_matrix.translation = bone_head_local
                
                # 赋值给骨骼矩阵
                bone.matrix = new_bone_matrix
                
                rotated_bones.append(bone)
                
        
        # 恢复原始选择状态
        bpy.ops.armature.select_all(action='DESELECT')
        for bone in selected_bones:
            bone.select = True
            bone.select_head = True
            bone.select_tail = True
        
        # 将成功移动的骨骼添加到骨骼集合中
        all_operated_bones = moved_bones + rotated_bones
        if all_operated_bones:
            # 创建或获取"骨骼操作"集合（更通用的名称）
            operated_collection = armature_obj.data.collections.get("骨骼操作")
            if not operated_collection:
                operated_collection = armature_obj.data.collections.new("骨骼操作")
            
            # 将成功操作的骨骼添加到集合并设置颜色
            for bone in all_operated_bones:
                operated_collection.assign(bone)
                bone.color.palette = theme_name
            
            info_msg = (
                f"成功操作 {len(all_operated_bones)} 个骨骼。 "
                f"{len(moved_bones)} 个骨骼尾部已对齐到选中子级平均头部； "
                f"{len(rotated_bones)} 个骨骼已继承父级矩阵 (无子级)。"
            )
            self.report({'INFO'}, info_msg)
        else:
            self.report({'WARNING'}, "没有符合条件的骨骼可以操作")
        
        return {'FINISHED'}


########################## Divider ##########################

class P_BoneEdit(bpy.types.Panel):
    bl_idname = "X_PT_BoneEdit"
    bl_label = "编辑模式"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XBone'

    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了此子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'BoneTools'

    def draw(self, context):
        layout = self.layout
        props = context.scene.bone_edit_world_props # 获取属性组
        if context.mode == "EDIT_ARMATURE":
            col = layout.column(align=True)
            row = col.row(align=True)
            row.operator(O_BoneEditYUp.bl_idname, text=O_BoneEditYUp.bl_label)
            row.operator(O_BoneEditZUp.bl_idname, text=O_BoneEditZUp.bl_label)
            row.operator(O_BoneEditUpRight.bl_idname, text=O_BoneEditUpRight.bl_label)
            #摆正后各方向旋转
            row = col.row(align=True)
            row.operator(O_BoneEditX90.bl_idname, text="X 90", icon="DRIVER_ROTATIONAL_DIFFERENCE")
            row.operator(O_BoneEditY90.bl_idname, text="Y 90", icon="DRIVER_ROTATIONAL_DIFFERENCE")
            row.operator(O_BoneEditZ90.bl_idname, text="Z 90", icon="DRIVER_ROTATIONAL_DIFFERENCE")

            row = col.row(align=True)
            row.operator(O_BoneConnect.bl_idname, text=O_BoneConnect.bl_label)       
            row.operator(O_BoneAllConnect.bl_idname, text=O_BoneAllConnect.bl_label)

            # 添加新的尾部对齐操作按钮
            row = col.row(align=True)
            row.operator(O_BoneMoveTailToChild.bl_idname, text=O_BoneMoveTailToChild.bl_label, icon='BONE_DATA')

            # 骨骼矩阵
            row = layout.row()
            active_object = context.active_object.name if context.active_object else "无活动对象"
            active_pose_bone = context.active_pose_bone.name if context.active_pose_bone else "无活动骨骼"
            row.label(text=f"{active_object}: {active_pose_bone}")
            row.prop(props, "edit_matrix", text="", icon='OBJECT_DATA', toggle=True)
            if props.edit_matrix:
                split = layout.split(align=True)
                col = split.column(align=True)
                col.label(text="基于骨架坐标系")
                col.prop(props, "edit_position", text="位置")
                col.prop(props, "edit_euler_rotation", text="欧拉")
                col.prop(props, "edit_quaternion_rotation", text="四元数")
                #col.prop(context.active_bone, "matrix", text="矩阵")
                col.label(text="矩阵:")
                row = col.row(align=True) #align消除间距
                row.prop(context.active_bone, "matrix", index=0, text="")
                row.prop(context.active_bone, "matrix", index=4, text="")
                row.prop(context.active_bone, "matrix", index=8, text="")
                row.prop(context.active_bone, "matrix", index=12, text="")
                row = col.row(align=True)
                row.prop(context.active_bone, "matrix", index=1, text="")
                row.prop(context.active_bone, "matrix", index=5, text="")
                row.prop(context.active_bone, "matrix", index=9, text="")
                row.prop(context.active_bone, "matrix", index=13, text="")
                row = col.row(align=True)
                row.prop(context.active_bone, "matrix", index=2, text="")
                row.prop(context.active_bone, "matrix", index=6, text="")
                row.prop(context.active_bone, "matrix", index=10, text="")
                row.prop(context.active_bone, "matrix", index=14, text="")
                row = col.row(align=True)
                row.prop(context.active_bone, "matrix", index=3, text="")
                row.prop(context.active_bone, "matrix", index=7, text="")
                row.prop(context.active_bone, "matrix", index=11, text="")
                row.prop(context.active_bone, "matrix", index=15, text="")

# 注册插件
def register():
    bpy.utils.register_class(O_BoneEditYUp)
    bpy.utils.register_class(O_BoneEditZUp)
    bpy.utils.register_class(O_BoneEditUpRight)
    bpy.utils.register_class(O_BoneEditX90)
    bpy.utils.register_class(O_BoneEditY90)
    bpy.utils.register_class(O_BoneEditZ90)
    bpy.utils.register_class(O_BoneConnect)
    bpy.utils.register_class(O_BoneAllConnect)
    bpy.utils.register_class(O_BoneMoveTailToChild)
    bpy.utils.register_class(P_BoneEdit)
    bpy.utils.register_class(PG_BoneEditWorldProps)
    bpy.types.Scene.bone_edit_world_props = bpy.props.PointerProperty(type=PG_BoneEditWorldProps)


# 注销插件
def unregister():
    bpy.utils.unregister_class(O_BoneEditYUp)
    bpy.utils.unregister_class(O_BoneEditZUp)
    bpy.utils.unregister_class(O_BoneEditUpRight)
    bpy.utils.unregister_class(O_BoneEditX90)
    bpy.utils.unregister_class(O_BoneEditY90)
    bpy.utils.unregister_class(O_BoneEditZ90)
    bpy.utils.unregister_class(O_BoneConnect)
    bpy.utils.unregister_class(O_BoneAllConnect)
    bpy.utils.unregister_class(O_BoneMoveTailToChild)
    bpy.utils.unregister_class(P_BoneEdit)
    bpy.utils.unregister_class(PG_BoneEditWorldProps)
    del bpy.types.Scene.bone_edit_world_props