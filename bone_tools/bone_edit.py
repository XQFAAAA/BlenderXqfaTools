# type: ignore
import bpy
import math
from mathutils import Euler, Matrix, Vector, Quaternion

########################## Divider ##########################

# 编辑骨骼变换数据剪贴板（模块级，无需注册）
# 形如 {'POSITION': Vector, 'EULER': Euler, 'QUATERNION': Quaternion, 'MATRIX': Matrix}
_bone_edit_clipboard = {}

class PG_BoneEditWorldProps(bpy.types.PropertyGroup):
    #注册切换矩阵显示的布尔值
    edit_matrix: bpy.props.BoolProperty(
        name="矩阵", 
        default=False,
        description="基于骨架坐标系"
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

class O_BoneEditUpRight(bpy.types.Operator):
    bl_idname = "xqfa.edit_upright"
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

########################## Divider ##########################

class O_BoneConnect(bpy.types.Operator):
    bl_idname = "xqfa.connect"
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
    bl_idname = "xqfa.all_connect"
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
    bl_idname = "xqfa.move_tail_to_child"
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

class O_BoneStraightenTwist(bpy.types.Operator):
    bl_idname = "xqfa.straighten_twist"
    bl_label = "摆正扭转"
    bl_description = "调整选中骨骼的扭转角度，使骨骼X轴与全局XY平面平行，且Z轴指向上方"

    def execute(self, context):
        if context.mode != 'EDIT_ARMATURE':
            self.report({'WARNING'}, "必须在骨骼编辑模式下运行此操作")
            return {'CANCELLED'}

        armature_obj = context.object
        if not armature_obj or armature_obj.type != 'ARMATURE':
            self.report({'WARNING'}, "未选择骨架对象")
            return {'CANCELLED'}

        selected_bones = context.selected_editable_bones
        if not selected_bones:
            self.report({'WARNING'}, "没有选中任何骨骼")
            return {'CANCELLED'}

        M = armature_obj.matrix_world.to_3x3()
        M_row2 = Vector((M[2][0], M[2][1], M[2][2]))

        count = 0
        for bone in selected_bones:
            bone_dir = bone.tail - bone.head
            if bone_dir.length < 1e-6:
                continue
            bone_dir.normalize()

            # 使 X_local 的全局 z 分量为 0，即 M_row2 · X_local = 0
            x_local = bone_dir.cross(M_row2)
            if x_local.length < 1e-6:
                x_local = Vector((0, 0, 1)).cross(bone_dir)
                if x_local.length < 1e-6:
                    x_local = Vector((1, 0, 0))
            x_local.normalize()

            z_local = x_local.cross(bone_dir)
            z_local.normalize()

            # 两种可能（X 翻转 ↔ Z 翻转），取 Z 全局 z > 0 的
            if M_row2.dot(z_local) < 0:
                x_local.negate()
                z_local = x_local.cross(bone_dir)
                z_local.normalize()

            # 计算当前 X 轴到目标 X 轴的绕 Y 轴旋转角，加到 roll
            current_x = bone.x_axis.normalized()
            cos_angle = current_x.dot(x_local)
            angle = math.acos(max(-1.0, min(1.0, cos_angle)))
            if current_x.cross(x_local).dot(bone_dir) < 0:
                angle = -angle

            bone.roll += angle
            count += 1

        self.report({'INFO'}, f"已摆正 {count} 个骨骼的扭转")
        return {'FINISHED'}


########################## Divider ##########################

class O_BoneEditCopyPaste(bpy.types.Operator):
    """复制/粘贴编辑骨骼变换数据（位置、欧拉、四元数、矩阵）"""
    bl_idname = "xqfa.edit_copy_paste"
    bl_label = "复制/粘贴"
    bl_description = "复制或粘贴编辑骨骼变换数据"
    bl_options = {'REGISTER', 'UNDO'}

    data_type: bpy.props.EnumProperty(
        name="数据类型",
        items=[
            ('POSITION', "位置", ""),
            ('EULER', "欧拉", ""),
            ('QUATERNION', "四元数", ""),
            ('MATRIX', "矩阵", ""),
        ],
    )
    action: bpy.props.EnumProperty(
        name="操作",
        items=[
            ('COPY', "复制", ""),
            ('PASTE', "粘贴", ""),
        ],
    )
    paste_order: bpy.props.EnumProperty(
        name="粘贴顺序",
        description="粘贴到多根骨骼时的应用顺序（父级到子级或子级到父级）",
        items=[
            ('NONE', "默认", "按选择顺序粘贴"),
            ('PARENT_TO_CHILD', "父到子", "先粘贴父级骨骼，再粘贴子级骨骼"),
            ('CHILD_TO_PARENT', "子到父", "先粘贴子级骨骼，再粘贴父级骨骼"),
        ],
        default='NONE',
    )

    # 数据类型中文名，用于 report
    _LABELS = {
        'POSITION': '位置', 'EULER': '欧拉',
        'QUATERNION': '四元数', 'MATRIX': '矩阵',
    }

    @classmethod
    def poll(cls, context):
        return (context.object and
                context.object.type == 'ARMATURE' and
                context.mode == 'EDIT_ARMATURE' and
                context.active_bone)

    def execute(self, context):
        bone = context.active_bone
        dt = self.data_type
        act = self.action
        label = self._LABELS[dt]

        if act == 'COPY':
            if dt == 'POSITION':
                _bone_edit_clipboard['POSITION'] = bone.matrix.translation.copy()
            elif dt == 'EULER':
                _bone_edit_clipboard['EULER'] = bone.matrix.to_euler().copy()
            elif dt == 'QUATERNION':
                _bone_edit_clipboard['QUATERNION'] = bone.matrix.to_quaternion().copy()
            elif dt == 'MATRIX':
                _bone_edit_clipboard['MATRIX'] = bone.matrix.copy()
            self.report({'INFO'}, f"已复制{label}")
            return {'FINISHED'}

        # PASTE：对所有选中骨骼生效
        if dt not in _bone_edit_clipboard:
            self.report({'WARNING'}, f"剪贴板中无{label}数据")
            return {'CANCELLED'}

        target_bones = context.selected_editable_bones or [bone]
        # 按父子级关系排序
        paste_order = self.paste_order
        if paste_order != 'NONE':
            selected_names = {b.name for b in target_bones}
            def selected_ancestor_count(b):
                count = 0
                parent = b.parent
                while parent is not None:
                    if parent.name in selected_names:
                        count += 1
                    parent = parent.parent
                return count
            target_bones = sorted(target_bones, key=selected_ancestor_count)
            if paste_order == 'CHILD_TO_PARENT':
                target_bones = list(reversed(target_bones))

        value = _bone_edit_clipboard[dt]
        pasted_count = 0
        for ebone in target_bones:
            if dt == 'POSITION':
                new_matrix = ebone.matrix.copy()
                new_matrix.translation = value
                ebone.matrix = new_matrix
            elif dt == 'EULER':
                new_matrix = value.to_matrix().to_4x4()
                new_matrix.translation = ebone.matrix.translation
                ebone.matrix = new_matrix
            elif dt == 'QUATERNION':
                new_matrix = value.to_matrix().to_4x4()
                new_matrix.translation = ebone.matrix.translation
                ebone.matrix = new_matrix
            elif dt == 'MATRIX':
                ebone.matrix = value.copy()
            pasted_count += 1

        context.view_layer.update()
        self.report({'INFO'}, f"已粘贴{label}到 {pasted_count} 根骨骼")
        return {'FINISHED'}


class P_BoneEdit(bpy.types.Panel):
    bl_idname = "X_PT_BoneEdit"
    bl_label = "编辑模式"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

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
            row.operator(O_BoneEditUpRight.bl_idname, text=O_BoneEditUpRight.bl_label)

            row = col.row(align=True)
            row.operator(O_BoneConnect.bl_idname, text=O_BoneConnect.bl_label)
            row.operator(O_BoneAllConnect.bl_idname, text=O_BoneAllConnect.bl_label)

            row = col.row(align=True)
            row.operator(O_BoneMoveTailToChild.bl_idname, text=O_BoneMoveTailToChild.bl_label, icon='BONE_DATA')

            row = col.row(align=True)
            row.operator(O_BoneStraightenTwist.bl_idname, text=O_BoneStraightenTwist.bl_label, icon='DRIVER_ROTATIONAL_DIFFERENCE')

            # 骨骼矩阵
            row = layout.row()
            active_object = context.active_object.name if context.active_object else "无活动对象"
            active_bone = context.active_bone.name if context.active_bone else "无活动骨骼"
            row.label(text=f"{active_object}: {active_bone}")
            row.prop(props, "edit_matrix", text="", icon='OBJECT_DATA', toggle=True)
            if props.edit_matrix:
                split = layout.split(align=True)
                col = split.column(align=True)
                row = col.row(align=True)
                row.label(text="位置")
                row.separator(factor=1.0)
                op = row.operator(O_BoneEditCopyPaste.bl_idname, text="", icon='COPYDOWN')
                op.data_type = 'POSITION'; op.action = 'COPY'
                op = row.operator(O_BoneEditCopyPaste.bl_idname, text="", icon='PASTEDOWN')
                op.data_type = 'POSITION'; op.action = 'PASTE'
                col.prop(props, "edit_position", text="")
                row = col.row(align=True)
                row.label(text="欧拉")
                row.separator(factor=1.0)
                op = row.operator(O_BoneEditCopyPaste.bl_idname, text="", icon='COPYDOWN')
                op.data_type = 'EULER'; op.action = 'COPY'
                op = row.operator(O_BoneEditCopyPaste.bl_idname, text="", icon='PASTEDOWN')
                op.data_type = 'EULER'; op.action = 'PASTE'
                col.prop(props, "edit_euler_rotation", text="")
                row = col.row(align=True)
                row.label(text="四元数")
                row.separator(factor=1.0)
                op = row.operator(O_BoneEditCopyPaste.bl_idname, text="", icon='COPYDOWN')
                op.data_type = 'QUATERNION'; op.action = 'COPY'
                op = row.operator(O_BoneEditCopyPaste.bl_idname, text="", icon='PASTEDOWN')
                op.data_type = 'QUATERNION'; op.action = 'PASTE'
                col.prop(props, "edit_quaternion_rotation", text="")
                #col.prop(context.active_bone, "matrix", text="矩阵")
                row = col.row(align=True)
                row.label(text="矩阵:")
                row.separator(factor=1.0)
                op = row.operator(O_BoneEditCopyPaste.bl_idname, text="", icon='COPYDOWN')
                op.data_type = 'MATRIX'; op.action = 'COPY'
                op = row.operator(O_BoneEditCopyPaste.bl_idname, text="", icon='PASTEDOWN')
                op.data_type = 'MATRIX'; op.action = 'PASTE'
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
classes = (
    PG_BoneEditWorldProps,
    O_BoneEditUpRight,
    O_BoneConnect,
    O_BoneAllConnect,
    O_BoneMoveTailToChild,
    O_BoneStraightenTwist,
    O_BoneEditCopyPaste,
    P_BoneEdit,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bone_edit_world_props = bpy.props.PointerProperty(type=PG_BoneEditWorldProps)


def unregister():
    del bpy.types.Scene.bone_edit_world_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)