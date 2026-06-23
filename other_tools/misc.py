# type: ignore
import bpy
from bpy.props import IntProperty, FloatProperty, PointerProperty
import re



# --- 界面面板 ---

class XQFA_PT_Demo(bpy.types.Panel):
    bl_label = "测试"
    bl_idname = "XQFA_PT_demo"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了此子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'OtherTools'
    
    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.operator(XQFA_OT_NumberToBone.bl_idname, icon="ARROW_LEFTRIGHT")
        col.operator(XQFA_OT_MiniPlane.bl_idname, icon="MESH_CUBE")
        col.operator(XQFA_OT_RenameComponents.bl_idname, icon="OUTLINER_OB_EMPTY")
        col.operator(XQFA_OT_SeparateByMaterial.bl_idname, icon="MATERIAL")
        col.operator(XQFA_OT_BatchCleanMaterials.bl_idname, icon="TRASH")
        col.operator(XQFA_OT_SelectWithChildren.bl_idname, icon='RESTRICT_SELECT_OFF')
        col.separator()
        col.operator(XQFA_OT_SelectMoreThan4.bl_idname, icon='CON_KINEMATIC')
        col.operator(XQFA_OT_SelectLessThan4.bl_idname, icon='CON_KINEMATIC')
        col.operator(XQFA_OT_SelectNegativeX.bl_idname, icon='FORWARD')
        col.operator(XQFA_OT_UndoTriSubdivide.bl_idname, icon='MESH_DATA')



# --- 算子 (Operators) ---

class XQFA_OT_MiniPlane(bpy.types.Operator):
    bl_idname = "xqfa.mini_plane"
    bl_label = "创建空模"
    bl_description = "创建一个极小的平面网格，并将其分配到两个顶点组中"
    bl_options = {'REGISTER', 'UNDO'}

    plane_size: FloatProperty(
        name="平面大小",
        description="平面的尺寸",
        default=0.0001,
        min=0.00001,
        max=0.001
    )

    primary_weight: FloatProperty(
        name="主权重",
        description="第一个顶点组的权重值",
        default=0.99,
        min=0.0,
        max=1.0
    )

    secondary_weight: FloatProperty(
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


class XQFA_OT_RenameComponents(bpy.types.Operator):
    """将选中物体名称中 C+数字 前缀替换为 Component +数字，同时也对每个物体的材质名执行相同匹配"""
    bl_idname = "xqfa.rename_to_components"
    bl_label = "重命名：C-->Components"
    bl_description = "匹配格式 C+数字(如C0-body) 替换为 Component +数字(如Component 0.-body)，同时对选中物体的材质名也执行相同匹配"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects

        if not selected_objects:
            self.report({'WARNING'}, "未选择任何物体")
            return {'CANCELLED'}

        rename_object_count = 0
        rename_material_count = 0

        # 正则表达式解释：
        # ^C : 匹配开头是大写字母 C
        # (\d+) : 匹配并捕获一个或多个数字
        # (.*) : 匹配并捕获之后的所有剩余字符
        pattern = re.compile(r"^C(\d+)(.*)")

        for obj in selected_objects:
            old_name = obj.name
            match = pattern.match(old_name)

            if match:
                number = match.group(1)
                suffix = match.group(2)
                new_name = f"Component {number}.{suffix}"
                obj.name = new_name
                rename_object_count += 1
                print(f"Renamed Object '{old_name}' -> '{new_name}'")
            else:
                print(f"Skipped Object '{old_name}' (格式不匹配)")

            # 对物体上的所有材质名执行相同匹配
            if obj.type == 'MESH' and obj.data.materials:
                for i, mat in enumerate(obj.data.materials):
                    if mat is None:
                        continue
                    old_mat_name = mat.name
                    mat_match = pattern.match(old_mat_name)
                    if mat_match:
                        mat_number = mat_match.group(1)
                        mat_suffix = mat_match.group(2)
                        new_mat_name = f"Component {mat_number}.{mat_suffix}"
                        mat.name = new_mat_name
                        rename_material_count += 1
                        print(f"Renamed Material '{old_mat_name}' -> '{new_mat_name}'")
                    else:
                        print(f"Skipped Material '{old_mat_name}' (格式不匹配)")

        self.report({'INFO'}, f"成功重命名 {rename_object_count} 个物体, {rename_material_count} 个材质")
        return {'FINISHED'}
    

    
class XQFA_OT_NumberToBone(bpy.types.Operator):
    bl_idname = "xqfa.num_to_bone"
    bl_label = "数字顶点组<-->骨骼名称"
    bl_description = "自动执行：合并->匹配重命名->排序->按材质分离->添加骨架"
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

        # --- 步骤 5: 合并选择物体 A B C D 到 A ---
        target_a = selected_others[0]
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_others:
            obj.select_set(True)
        context.view_layer.objects.active = target_a
        bpy.ops.object.join()

        # --- 步骤 6: 执行匹配重命名 (E 为源, A 为目标) ---
        bpy.ops.object.select_all(action='DESELECT')
        active_e.select_set(True)
        target_a.select_set(True)
        context.view_layer.objects.active = target_a
        
        try:
            bpy.ops.xqfa.vertex_groups_match_rename()
        except Exception as e:
            self.report({'WARNING'}, f"匹配重命名失败: {e}")

        # --- 步骤 7: 执行名称排序 (A 为源, E 为目标) ---
        bpy.ops.object.select_all(action='DESELECT')
        target_a.select_set(True)
        active_e.select_set(True)
        context.view_layer.objects.active = target_a
        
        try:
            bpy.ops.xqfa.vertex_groups_sort_match()
        except Exception as e:
            self.report({'WARNING'}, f"排序失败: {e}")

        # --- 步骤 8: 按材质分离 A (使用材质名作为分离后物体名称) ---
        bpy.ops.object.select_all(action='DESELECT')
        target_a.select_set(True)
        context.view_layer.objects.active = target_a
        
        try:
            bpy.ops.xqfa.separate_by_material(naming_mode='MATERIAL')
        except Exception as e:
            self.report({'WARNING'}, f"按材质分离失败: {e}")

        separated_objs = context.selected_objects

        # === 添加骨架 ===
        bpy.ops.object.select_all(action='DESELECT')
        for obj in separated_objs:
            if obj.type == 'MESH':
                obj.select_set(True)
        context.view_layer.objects.active = active_e

        armature_modifiers = [mod for mod in active_e.modifiers if mod.type == 'ARMATURE']
        if armature_modifiers:
            src_mod = armature_modifiers[0]
            for obj in separated_objs:
                if obj.type == 'MESH':
                    new_mod = obj.modifiers.new(name="Armature", type='ARMATURE')
                    new_mod.object = src_mod.object
                    new_mod.use_bone_envelopes = src_mod.use_bone_envelopes
                    new_mod.use_vertex_groups = src_mod.use_vertex_groups
                    new_mod.use_deform_preserve_volume = src_mod.use_deform_preserve_volume
                    new_mod.vertex_group = src_mod.vertex_group

        self.report({'INFO'}, "已完成合并、匹配重命名、排序、按材质分离及添加骨架")
        return {'FINISHED'}


class XQFA_OT_BatchCleanMaterials(bpy.types.Operator):
    """对选中的所有物体删除未使用的材质槽"""
    bl_idname = "xqfa.batch_clean_materials"
    bl_label = "批量清理材质"
    bl_description = "对选中的所有物体删除未使用的材质槽"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and len(context.selected_objects) > 0

    def execute(self, context):
        objs = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not objs:
            self.report({'WARNING'}, "未选中任何网格物体")
            return {'CANCELLED'}

        cleaned_count = 0
        for obj in objs:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj

            slots_before = len(obj.material_slots)
            if slots_before == 0:
                continue

            bpy.ops.object.material_slot_remove_unused()
            slots_after = len(obj.material_slots)
            if slots_before != slots_after:
                cleaned_count += 1

        self.report({'INFO'}, f"已清理 {cleaned_count} 个物体的未使用材质槽")
        return {'FINISHED'}


class XQFA_OT_SeparateByMaterial(bpy.types.Operator):
    bl_idname = "xqfa.separate_by_material"
    bl_label = "按材质分离"
    bl_description = "按材质分离物体"
    bl_options = {'REGISTER', 'UNDO'}

    naming_mode: bpy.props.EnumProperty(
        name="命名方式",
        items=[
            ('MATERIAL', "材质名", "使用材质名作为分离后的物体名称"),
            ('ORIGINAL_MATERIAL', "原名_材质名", "使用{原名}_{材质名}作为分离后的物体名称"),
        ],
        default='ORIGINAL_MATERIAL'
    )

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and any(obj.type == 'MESH' for obj in context.selected_objects)

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=220)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "naming_mode", expand=True)

    def execute(self, context):
        mesh_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not mesh_objects:
            self.report({'WARNING'}, "未选中任何网格物体")
            return {'CANCELLED'}

        total_count = 0

        for obj in mesh_objects:
            if not obj.data.materials:
                self.report({'WARNING'}, f"物体 {obj.name} 没有材质，已跳过")
                continue

            original_name = obj.name

            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.separate(type='MATERIAL')
            bpy.ops.object.mode_set(mode='OBJECT')

            separated_objs = context.selected_objects
            for sep_obj in separated_objs:
                if sep_obj.type == 'MESH' and sep_obj.data.materials:
                    mat_name = sep_obj.data.materials[0].name
                    if self.naming_mode == 'MATERIAL':
                        sep_obj.name = mat_name
                    else:
                        sep_obj.name = f"{original_name}_{mat_name}"

            total_count += len(separated_objs)

        self.report({'INFO'}, f"已按材质分离共 {total_count} 个物体")
        return {'FINISHED'}





class XQFA_OT_SelectMoreThan4(bpy.types.Operator):
    bl_idname = "xqfa.select_more_than_4"
    bl_label = "选择连线>4的顶点"
    bl_description = "在编辑模式中，从选中顶点里选出连线数大于4的顶点"
    bl_options = {'REGISTER', 'UNDO'}

    include_boundary: bpy.props.BoolProperty(
        name="包括边界点",
        description="是否包括边界顶点",
        default=True
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        import bmesh
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        selected_verts = [v for v in bm.verts if v.select]
        if not selected_verts:
            self.report({'WARNING'}, "没有选中的顶点")
            return {'CANCELLED'}

        count = 0
        for v in selected_verts:
            is_boundary = any(e.is_boundary for e in v.link_edges)
            if len(v.link_edges) > 4:
                if self.include_boundary or not is_boundary:
                    v.select = True
                    count += 1
                else:
                    v.select = False
            else:
                v.select = False

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"已选择 {count} 个连线>4的顶点")
        return {'FINISHED'}


class XQFA_OT_SelectLessThan4(bpy.types.Operator):
    bl_idname = "xqfa.select_less_than_4"
    bl_label = "选择连线<4的顶点"
    bl_description = "在编辑模式中，从选中顶点里选出连线数小于4的顶点"
    bl_options = {'REGISTER', 'UNDO'}

    include_boundary: bpy.props.BoolProperty(
        name="包括边界点",
        description="是否包括边界顶点",
        default=True
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        import bmesh
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        selected_verts = [v for v in bm.verts if v.select]
        if not selected_verts:
            self.report({'WARNING'}, "没有选中的顶点")
            return {'CANCELLED'}

        count = 0
        for v in selected_verts:
            is_boundary = any(e.is_boundary for e in v.link_edges)
            if len(v.link_edges) < 4:
                if self.include_boundary or not is_boundary:
                    v.select = True
                    count += 1
                else:
                    v.select = False
            else:
                v.select = False

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"已选择 {count} 个连线<4的顶点")
        return {'FINISHED'}


class XQFA_OT_SelectNegativeX(bpy.types.Operator):
    bl_idname = "xqfa.select_negative_x"
    bl_label = "选择X<0的顶点"
    bl_description = "在编辑模式中，选择X坐标小于0的顶点"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        import bmesh
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        bpy.ops.mesh.select_all(action='DESELECT')

        count = 0
        for v in bm.verts:
            if v.co.x < 0.0:
                v.select = True
                count += 1

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"已选择 {count} 个X<0的顶点")
        return {'FINISHED'}


class XQFA_OT_UndoTriSubdivide(bpy.types.Operator):
    bl_idname = "xqfa.undo_tri_subdivide"
    bl_label = "还原三角面中点细分"
    bl_description = ("还原三角面中点细分为四边面的操作：\n"
                      "1. 选择非边界的连线=3的顶点（三角面中心）\n"
                      "2. 选择与这些点相连的顶点（各边中点）\n"
                      "3. 融并这些顶点之间的边")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        import bmesh
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        center_verts = set()
        for v in bm.verts:
            if len(v.link_edges) == 3:
                is_boundary = any(e.is_boundary for e in v.link_edges)
                if not is_boundary:
                    center_verts.add(v)

        if not center_verts:
            self.report({'WARNING'}, "没有找到非边界且连线=3的顶点")
            return {'CANCELLED'}

        midpoint_verts = set()
        for cv in center_verts:
            for e in cv.link_edges:
                midpoint_verts.add(e.other_vert(cv))

        all_subdiv_verts = center_verts | midpoint_verts
        edges_to_dissolve = set()
        for v in all_subdiv_verts:
            for e in v.link_edges:
                other = e.other_vert(v)
                if other in all_subdiv_verts:
                    edges_to_dissolve.add(e)

        bmesh.ops.dissolve_edges(bm, edges=list(edges_to_dissolve), use_verts=True)

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"已还原 {len(center_verts)} 个三角面的细分")
        return {'FINISHED'}


class XQFA_OT_SelectWithChildren(bpy.types.Operator):
    """选择选中对象及其所有子级（包括隐藏的）"""
    bl_idname = "xqfa.select_with_children"
    bl_label = "选择对象及全部子级"
    bl_description = "选择选中对象及其所有子级对象（包括子级的子级，即使隐藏也能选择）"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        """检查是否有选中的对象"""
        return context.selected_objects is not None and len(context.selected_objects) > 0
    
    def get_all_children(self, obj):
        """递归获取所有子级对象"""
        all_children = []
        
        def collect_children(parent):
            for child in parent.children:
                all_children.append(child)
                collect_children(child)
        
        collect_children(obj)
        return all_children
    
    def execute(self, context):
        """执行选择操作"""
        selected_objects = list(context.selected_objects)
        
        if not selected_objects:
            self.report({'WARNING'}, "未选择任何对象")
            return {'CANCELLED'}
        
        # 收集所有要选择的对象（包括选中对象和它们的所有子级）
        objects_to_select = []
        for obj in selected_objects:
            objects_to_select.append(obj)
            objects_to_select.extend(self.get_all_children(obj))
        
        # 保存原始模式
        original_mode = None
        if context.active_object:
            original_mode = context.active_object.mode
        
        # 切换到对象模式
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # 取消所有选择
        bpy.ops.object.select_all(action='DESELECT')
        
        # 选择并显示所有要选择的对象
        select_count = 0
        for obj in objects_to_select:
            # 确保对象在场景中且可以被选择
            if obj and obj.name in bpy.data.objects:
                try:
                    # 显示对象（取消隐藏）
                    obj.hide_set(False)
                    obj.hide_viewport = False
                    obj.hide_render = False
                    # 选择对象
                    obj.select_set(True)
                    select_count += 1
                except:
                    pass
        
        # 设置活动对象为第一个选中的对象
        if select_count > 0:
            for obj in objects_to_select:
                if obj and obj.name in bpy.data.objects:
                    context.view_layer.objects.active = obj
                    break
            self.report({'INFO'}, f"已选择 {select_count} 个对象")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "没有找到可选择的对象")
            return {'CANCELLED'}




classes = (
    XQFA_PT_Demo,
    XQFA_OT_NumberToBone,
    XQFA_OT_MiniPlane,
    XQFA_OT_RenameComponents,
    XQFA_OT_SeparateByMaterial,
    XQFA_OT_BatchCleanMaterials,
    XQFA_OT_SelectWithChildren,
    XQFA_OT_SelectMoreThan4,
    XQFA_OT_SelectLessThan4,
    XQFA_OT_SelectNegativeX,
    XQFA_OT_UndoTriSubdivide,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)




def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    

