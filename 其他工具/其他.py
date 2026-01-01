# type: ignore
import bpy
from bpy.props import IntProperty
import mathutils
from mathutils import Vector
import math
import re

class ObjType(bpy.types.Operator):
    def is_mesh(scene, obj):
        return obj.type == "MESH"
    
    def is_armature(scene, obj):
        return obj.type == "ARMATURE"

class P_DEMO(bpy.types.Panel):
    bl_label = "测试"
    bl_idname = "X_PT_DEMO"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了此子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'OtherTools'
    
    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator(X_OT_NumberToBone.bl_idname, icon="ARROW_LEFTRIGHT")
        col.operator(MiniPlaneOperator.bl_idname, icon="MESH_CUBE")
        col.operator(RenameToComponents.bl_idname, icon="OUTLINER_OB_EMPTY")
        col.operator(TANGENTSPACE_OCTAHEDRAL_UV_OT_operator.bl_idname, icon='UV')

        box = layout.box()
        col = box.column(align=True)
        col.prop(context.scene, "sk_source_mesh", text = "", icon="MESH_DATA")
        if context.scene.sk_source_mesh:
            armature_mod = None
            armature_modifiers = [mod for mod in context.scene.sk_source_mesh.modifiers if mod.type == 'ARMATURE']
            
            if armature_modifiers:
                if len(armature_modifiers) == 1:
                    armature_mod = armature_modifiers[0]
                    col.label(text=f"骨架: {armature_mod.object.name if armature_mod.object else '无'}", icon='ARMATURE_DATA')
                else:
                    col.label(text="错误: 物体有多个骨架修改器", icon='ERROR')
            else:
                col.label(text="错误: 物体没有骨架修改器", icon='ERROR')
        col.operator(ApplyAsShapekey.bl_idname, icon="SHAPEKEY_DATA")

        



class MiniPlaneOperator(bpy.types.Operator):
    bl_idname = "xqfa.mini_plane"
    bl_label = "创建空模"
    bl_description = "创建一个极小的平面网格，并将其分配到两个顶点组中"
    bl_options = {'REGISTER', 'UNDO'}

    plane_size: bpy.props.FloatProperty(
        name="平面大小",
        description="平面的尺寸",
        default=0.0001,
        min=0.00001,
        max=0.001
    )

    primary_weight: bpy.props.FloatProperty(
        name="主权重",
        description="第一个顶点组的权重值",
        default=0.99,
        min=0.0,
        max=1.0
    )

    secondary_weight: bpy.props.FloatProperty(
        name="次权重",
        description="第二个顶点组的权重值",
        default=0.02,
        min=0.0,
        max=1.0
    )

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None

    def execute(self, context):
        # 获取当前选中的物体
        selected_objects = context.selected_objects

        for obj in selected_objects:
            # 确保物体是网格类型
            if obj.type != 'MESH':
                self.report({'WARNING'}, f"物体 {obj.name} 不是网格类型，已跳过")
                continue

            # 只选择当前物体
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='EDIT')

            # 选择所有顶点并删除
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.delete(type='VERT')

            # 添加平面网格
            bpy.ops.mesh.primitive_plane_add(size=1, enter_editmode=True)

            # 缩放平面到极小尺寸
            bpy.ops.transform.resize(value=(self.plane_size, self.plane_size, self.plane_size))

            # 返回对象模式
            bpy.ops.object.mode_set(mode='OBJECT')

            # 确保至少有两个顶点组
            if len(obj.vertex_groups) < 2:
                # 清除现有顶点组
                for vg in obj.vertex_groups:
                    obj.vertex_groups.remove(vg)
                
                # 创建两个新的顶点组
                vg1 = obj.vertex_groups.new(name="0")
                vg2 = obj.vertex_groups.new(name="1")

            # 获取顶点组引用
            vg1 = obj.vertex_groups[0]
            vg2 = obj.vertex_groups[1]

            # 获取网格数据
            mesh = obj.data
            vertices = mesh.vertices

            # 将四个顶点分配到两个顶点组
            for v in vertices:
                vg1.add([v.index], self.primary_weight, 'REPLACE')
                vg2.add([v.index], self.secondary_weight, 'REPLACE')

            self.report({'INFO'}, 
                f"已处理物体: {obj.name}\n"
                f"顶点组1({vg1.name})权重: {self.primary_weight}\n"
                f"顶点组2({vg2.name})权重: {self.secondary_weight}"
            )

        return {'FINISHED'}


class RenameToComponents(bpy.types.Operator):
    bl_idname = "xqfa.rename_to_components"
    bl_label = "重命名：C-->Components"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        
        if not selected_objects:
            self.report({'WARNING'}, "未选择任何物体")
            return {'CANCELLED'}
        
        # 统计重命名的数量
        rename_count = 0
        
        # 正则表达式解释：
        # ^C : 匹配开头是大写字母 C
        # (\d+) : 匹配并捕获一个或多个数字
        # (.*) : 匹配并捕获之后的所有剩余字符
        pattern = re.compile(r"^C(\d+)(.*)")

        for obj in selected_objects:
            old_name = obj.name
            match = pattern.match(old_name)
            
            if match:
                number = match.group(1)   # 提取数字，例如 "2"
                suffix = match.group(2)   # 提取后缀，例如 "-body"
                
                # 拼接新名称：Component {数字}.{后缀}
                new_name = f"Component {number}.{suffix}"
                
                obj.name = new_name
                rename_count += 1
                print(f"Renamed '{old_name}' -> '{new_name}'")
            else:
                # 如果名称不符合 C0, C1 这种格式，则跳过
                print(f"Skipped '{old_name}' (格式不匹配)")

        self.report({'INFO'}, f"成功重命名 {rename_count} 个物体")
        return {'FINISHED'}
    
class ApplyAsShapekey(bpy.types.Operator):
    bl_idname = "xqfa.apply_as_shapekey"
    bl_label = "应用为形态键"
    bl_description = "将当前骨架的姿态应用为目标物体的形态键"
    bl_options = {'REGISTER', 'UNDO'}
    
    def find_armature_modifier(self, obj):
        """查找物体的骨架修改器"""
        armature_modifiers = [mod for mod in obj.modifiers if mod.type == 'ARMATURE']
        
        if not armature_modifiers:
            self.report({'ERROR'}, "物体没有骨架修改器")
            return None
            
        if len(armature_modifiers) > 1:
            self.report({'ERROR'}, "物体有多个骨架修改器")
            return None
            
        return armature_modifiers[0]
    
    def execute(self, context):
        # 检查目标物体
        try:
            obj = bpy.data.objects.get(context.scene.sk_source_mesh.name)
        except:
            self.report({'ERROR'}, "似乎没有选择对象") 
            return {'FINISHED'}
            
        
        # 查找骨架修改器
        armature_mod = self.find_armature_modifier(obj)
        if not armature_mod:
            return {'CANCELLED'}
            
        armature = armature_mod.object
        if not armature:
            self.report({'ERROR'}, "骨架修改器没有指定骨架")
            return {'CANCELLED'}
            
        # 切换到物体模式
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = obj

        # 确保物体有形态键
        if not obj.data.shape_keys:
            obj.shape_key_add(name="Basis", from_mix=False)
            
        # 使用骨架修改器的保存为形态键功能
        try:
            bpy.ops.object.modifier_apply_as_shapekey(keep_modifier=True, modifier=armature_mod.name)
            self.report({'INFO'}, f"已为 {obj.name} 从骨架修改器创建形态键")
        except Exception as e:
            self.report({'ERROR'}, f"应用形态键失败: {str(e)}")
            return {'CANCELLED'}
        finally:
            # 切换回姿态模式并清空变换
            bpy.context.view_layer.update()
            bpy.context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode='POSE')
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.transforms_clear()
        
        return {'FINISHED'}
    
class X_OT_NumberToBone(bpy.types.Operator):
    bl_idname = "xqfa.num_to_bone"
    bl_label = "数字顶点组<-->骨骼名称"
    bl_description = "自动执行：清除材质->按名分配材质->合并->匹配重命名->排序->按材质分离->添加骨架->匹配材质"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and len(context.selected_objects) > 1

    def execute(self, context):
        # 1. 获取初始状态
        active_e = context.active_object
        selected_others = [obj for obj in context.selected_objects if obj != active_e and obj.type == 'MESH']
        
        if not selected_others:
            self.report({'ERROR'}, "请选择除活动物体外的至少一个网格物体")
            return {'CANCELLED'}

        # --- 步骤 3 & 4: 清除材质并添加以物体名命名的默认材质 ---
        for obj in selected_others:
            obj.data.materials.clear()
            new_mat = bpy.data.materials.new(name=obj.name)
            obj.data.materials.append(new_mat)

        # --- 步骤 5: 合并选择物体 A B C D 到 A ---
        # 我们将第一个选中的物体作为合并目标（即你的 A）
        target_a = selected_others[0]
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_others:
            obj.select_set(True)
        context.view_layer.objects.active = target_a
        bpy.ops.object.join()
        # 此时 target_a 是合并后的物体，包含了原 A B C D 的所有数据

        # --- 步骤 6: 执行匹配重命名 (E 为源, A 为目标) ---
        # O_VertexGroupsMatchRename 逻辑：B(活动) 被 A(非活动) 重命名
        # 用户需求：E 为选择，A 为活动
        bpy.ops.object.select_all(action='DESELECT')
        active_e.select_set(True)
        target_a.select_set(True)
        context.view_layer.objects.active = target_a
        
        try:
            bpy.ops.xqfa.vertex_groups_match_rename()
        except Exception as e:
            self.report({'WARNING'}, f"匹配重命名失败: {e}")

        # --- 步骤 7: 执行名称排序 (A 为源, E 为目标) ---
        # O_VertexGroupsSortMatch 逻辑：B(活动) 匹配 A(非活动) 的顺序
        # 用户需求：A 为选择，E 为活动
        bpy.ops.object.select_all(action='DESELECT')
        target_a.select_set(True)
        active_e.select_set(True)
        context.view_layer.objects.active = active_e
        
        try:
            bpy.ops.xqfa.vertex_groups_sort_match()
        except Exception as e:
            self.report({'WARNING'}, f"排序失败: {e}")

        # --- 步骤 8: 按材质分离 A 并重命名 ---
        bpy.ops.object.select_all(action='DESELECT')
        target_a.select_set(True)
        context.view_layer.objects.active = target_a
        
        # 进入编辑模式分离
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='MATERIAL')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # --- 步骤 9: 将物体名称改回其对应的材质名称，删除材质 ---
        separated_objs = context.selected_objects
        for obj in separated_objs:
            if obj.type == 'MESH' and obj.data.materials:
                obj.name = obj.data.materials[0].name
                obj.data.materials.clear()

        # === 新增复制骨架 ===
        # 放弃所有选择，将分解出的A B C D作为选择物体，E作为活动物体
        bpy.ops.object.select_all(action='DESELECT')
        for obj in separated_objs:
            if obj.type == 'MESH':
                obj.select_set(True)
        context.view_layer.objects.active = active_e
        
        # 对E的骨架修改器执行"复制到选定项操作"
        # 查找E物体上的骨架修改器
        armature_modifiers = [mod for mod in active_e.modifiers if mod.type == 'ARMATURE']
        if armature_modifiers:
            # 如果有骨架修改器，将其复制到选中的物体
            for obj in separated_objs:
                if obj.type == 'MESH':
                    # 为每个分离出的物体添加骨架修改器
                    new_mod = obj.modifiers.new(name="Armature", type='ARMATURE')
                    # 复制E的骨架修改器设置
                    src_mod = armature_modifiers[0]
                    new_mod.object = src_mod.object
                    new_mod.use_bone_envelopes = src_mod.use_bone_envelopes
                    new_mod.use_vertex_groups = src_mod.use_vertex_groups
                    new_mod.use_deform_preserve_volume = src_mod.use_deform_preserve_volume
                    new_mod.vertex_group = src_mod.vertex_group
        # === 新增步骤结束 ===

        # --- 步骤 10: 计算分离物体的面数 ---
        def get_face_count(obj):
            """获取物体的面数"""
            if obj.type == 'MESH':
                return len(obj.data.polygons)
            return 0
        
        # 存储分离物体的面数
        obj_face_counts = {}
        for obj in separated_objs:
            face_count = get_face_count(obj)
            if face_count > 0:
                obj_face_counts[obj] = face_count
        
        # --- 步骤 11: 计算E物体每个材质区域的面数 ---
        e_mesh = active_e.data
        mat_face_counts = {}  # {材质索引: 面数}
        
        # 按材质索引统计面数
        for poly in e_mesh.polygons:
            mat_index = poly.material_index
            if mat_index not in mat_face_counts:
                mat_face_counts[mat_index] = 0
            mat_face_counts[mat_index] += 1
        
        # --- 步骤 12: 根据面数匹配并赋予E的材质 ---
        match_count = 0
        
        # 对于每个分离物体，找到面数最接近的材质
        for obj, obj_face_count in obj_face_counts.items():
            best_match_idx = -1
            min_face_diff = float('inf')
            
            for mat_idx, mat_face_count in mat_face_counts.items():
                face_diff = abs(obj_face_count - mat_face_count)
                if face_diff < min_face_diff:
                    min_face_diff = face_diff
                    best_match_idx = mat_idx
            
            # 如果找到匹配的材质
            if best_match_idx != -1:
                # 获取对应的材质
                if best_match_idx < len(active_e.material_slots):
                    orig_mat = active_e.material_slots[best_match_idx].material
                    if orig_mat:
                        # 赋予材质
                        obj.data.materials.clear()
                        obj.data.materials.append(orig_mat)
                        match_count += 1
                        
                        # 从候选列表中移除已匹配的材质，避免重复匹配
                        # 注意：这可能会导致某些材质没有被分配，但更符合一一对应的逻辑
                        del mat_face_counts[best_match_idx]
        
        self.report({'INFO'}, f"已匹配顶点组，已匹配 {match_count} 个材质")
        return {'FINISHED'}
    

def unit_vector_to_octahedron(n):
    """
    Converts a unit vector to octahedron coordinates.
    n is a mathutils.Vector
    """
    # 确保输入是单位向量
    if n.length_squared > 1e-10:
        n.normalize()
    else:
        return Vector((0.0, 0.0))
    
    # 计算L1范数
    l1_norm = abs(n.x) + abs(n.y) + abs(n.z)
    if l1_norm < 1e-10:
        return Vector((0.0, 0.0))
    
    # 投影到八面体平面
    x = n.x / l1_norm
    y = n.y / l1_norm
    
    # 负半球映射（仅在z<0时应用）
    if n.z < 0:
        # 使用精确的符号函数
        sign_x = math.copysign(1.0, x)
        sign_y = math.copysign(1.0, y)
        
        # 原始映射公式（保留在z=0处的良好行为）
        new_x = (1.0 - abs(y)) * sign_x
        new_y = (1.0 - abs(x)) * sign_y
        
        # 直接应用新坐标（移除过渡插值）
        x = new_x
        y = new_y
    
    return Vector((x, y))

def calc_smooth_normals(mesh):
    """计算平滑法线（角度加权平均）"""
    vertex_normals = {}
    
    # 使用顶点索引作为键（避免浮点精度问题）
    for i, vert in enumerate(mesh.vertices):
        vertex_normals[i] = Vector((0, 0, 0))
    
    # 计算每个面的法线并加权累加到顶点
    for poly in mesh.polygons:
        verts = [mesh.vertices[i] for i in poly.vertices]
        face_normal = poly.normal
        
        for i, vert in enumerate(verts):
            # 获取相邻边向量
            v1 = verts[(i+1) % len(verts)].co - vert.co
            v2 = verts[(i-1) % len(verts)].co - vert.co
            
            # 计算角度权重
            v1_len = v1.length
            v2_len = v2.length
            if v1_len > 1e-6 and v2_len > 1e-6:
                v1.normalize()
                v2.normalize()
                weight = math.acos(max(-1.0, min(1.0, v1.dot(v2))))
            else:
                weight = 0.0
            
            # 累加加权法线
            vertex_normals[vert.index] += face_normal * weight
    
    # 归一化法线
    for idx in vertex_normals:
        if vertex_normals[idx].length > 1e-6:
            vertex_normals[idx].normalize()
    
    return vertex_normals

class TANGENTSPACE_OCTAHEDRAL_UV_OT_operator(bpy.types.Operator):
    """生成切线空间的八面体UV映射"""
    bl_idname = "xqfa.octahedral_uv"
    bl_label = "平滑法线-八面体UV"
    bl_description = ("对所有选中物体\n"
    "平滑法线在切线空间的坐标，投射八面体展开平面\n"
    "存储在TEXCOORD1\n"
    "为了计算切线空间，必须要有一个正常展开的uv")
    bl_options = {'REGISTER', 'UNDO'}
    
    
    @classmethod
    def poll(cls, context):
        """检查是否可以选择网格物体"""
        return context.selected_objects is not None and len(context.selected_objects) > 0
    
    def execute(self, context):
        """执行操作"""
        selected_objects = context.selected_objects
        processed_count = 0
        
        for obj in selected_objects:
            if self.process_object(obj):
                processed_count += 1
        
        # 更新显示
        context.view_layer.update()
        
        if processed_count > 0:
            self.report({'INFO'}, f"切线空间八面体UV映射完成！共处理 {processed_count} 个网格物体")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "没有处理任何网格物体，请确保选中了网格物体")
            return {'CANCELLED'}
    
    def process_object(self, obj):
        """处理单个网格物体"""
        if obj.type != 'MESH':
            return False
            
        mesh = obj.data
        
        # 确保在对象模式（数据一致）
        if bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # 操作前将活动UV设置为第一个（索引0）
        if len(mesh.uv_layers) > 0:
            mesh.uv_layers.active_index = 0
        
        # 计算平滑法线
        smooth_normals = calc_smooth_normals(mesh)
        
        # 确保网格有UV层（计算切线需要）
        if len(mesh.uv_layers) == 0:
            mesh.uv_layers.new(name="UVMap")
        
        # 计算切线空间（TBN矩阵）
        mesh.calc_tangents()
        
        # 创建/获取UV层
        uv_layer_name = "TEXCOORD1.xy"
        if uv_layer_name in mesh.uv_layers:
            uv_layer = mesh.uv_layers[uv_layer_name]
        else:
            uv_layer = mesh.uv_layers.new(name=uv_layer_name)
        
        # 处理每个面的每个顶点
        for poly in mesh.polygons:
            for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                loop = mesh.loops[loop_idx]
                vertex_idx = loop.vertex_index
                
                # 获取平滑法线
                normal = smooth_normals[vertex_idx]

                # 构建TBN矩阵（切线空间到模型空间的变换）
                tbn_matrix = mathutils.Matrix((
                    loop.tangent,
                    loop.bitangent,
                    loop.normal
                )).transposed() # 转置以从行向量变为列向量
                
                # 检查矩阵是否可逆
                try:
                    # 尝试计算逆矩阵
                    tbn_inverse = tbn_matrix.inverted()
                    
                    # 将法线从模型空间转换到切线空间
                    tangent_normal = tbn_inverse @ normal
                    tangent_normal.normalize()
                except ValueError:
                    # 矩阵不可逆时的回退方案
                    print(f"警告: 顶点 {vertex_idx} 的TBN矩阵不可逆，使用默认法线")
                    
                    tangent_normal = Vector((0, 0, 1))  # 默认使用Z轴作为法线
                
                # 八面体投影
                oct_coords = unit_vector_to_octahedron(tangent_normal)
                
                # 设置UV
                u = oct_coords.x
                v = oct_coords.y + 1.0
                uv_layer.data[loop_idx].uv = (u, v)
        
        # 释放切线数据
        mesh.free_tangents()
        
        return True


def register():
    bpy.utils.register_class(P_DEMO)
    bpy.utils.register_class(X_OT_NumberToBone)
    bpy.utils.register_class(MiniPlaneOperator)
    bpy.utils.register_class(RenameToComponents)
    bpy.utils.register_class(ApplyAsShapekey)
    bpy.types.Scene.sk_source_mesh = bpy.props.PointerProperty(
        description="选择编辑形态键的物体",
        type=bpy.types.Object, 
        poll=ObjType.is_mesh
        )

    bpy.utils.register_class(TANGENTSPACE_OCTAHEDRAL_UV_OT_operator)


def unregister():
    bpy.utils.unregister_class(P_DEMO)
    bpy.utils.unregister_class(X_OT_NumberToBone)
    bpy.utils.unregister_class(MiniPlaneOperator)
    bpy.utils.unregister_class(RenameToComponents)
    bpy.utils.unregister_class(ApplyAsShapekey)
    del bpy.types.Scene.sk_source_mesh

    bpy.utils.unregister_class(TANGENTSPACE_OCTAHEDRAL_UV_OT_operator)


