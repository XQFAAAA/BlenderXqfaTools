# type: ignore
import bpy
from bpy.props import EnumProperty


# --- 界面面板 ---

class XQFA_PT_WWMI(bpy.types.Panel):
    bl_label = "WWMI"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了其他工具子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'OtherTools'

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.operator(XQFA_OT_SyncExtractUnpack.bl_idname, icon="UV_SYNC_SELECT")
        col.operator(XQFA_OT_WWAttributePreset.bl_idname, icon="PRESET")


# --- 算子 (Operators) ---

class XQFA_OT_SyncExtractUnpack(bpy.types.Operator):
    bl_idname = "xqfa.sync_extract_unpack"
    bl_label = "同步提取和解包"
    bl_description = "合并/分离模式：匹配材质、顶点组、形态键并添加骨架"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(
        name="模式",
        items=[
            ('MERGE', "合并", "合并模式：合并物体后匹配并分离"),
            ('SEPARATE', "分离", "分离模式：复制活动物体分离后逐个匹配"),
        ],
        default='MERGE'
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and len(context.selected_objects) > 1

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=200)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)

    def execute(self, context):
        if self.mode == 'MERGE':
            return self._execute_merge(context)
        else:
            return self._execute_separate(context)

    # ========== 辅助函数 ==========

    @staticmethod
    def _get_mapping_name(obj_name):
        """映射名称 = 物体名称按下划线分割后的第二个元素，无则用原名"""
        parts = obj_name.split("_")
        if len(parts) > 1:
            return parts[1]
        return obj_name

    @staticmethod
    def _find_common_prefix(strings):
        """查找字符串列表的最长公共前缀"""
        if not strings:
            return ""
        prefix = strings[0]
        for s in strings[1:]:
            while not s.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    return ""
        return prefix

    @staticmethod
    def _strip_common_prefix(name, prefix):
        """去除名称的公共前缀，名称不以该前缀开头时原样返回"""
        if prefix and name.startswith(prefix):
            return name[len(prefix):]
        return name

    @classmethod
    def _derive_part_name(cls, mat_name, obj_name, common_prefix):
        """从材质名推导部位名：去掉公共前缀，再去掉材质名中与活动物体名相同的标识部分"""
        part = cls._strip_common_prefix(mat_name, common_prefix)
        end = 0
        for token in obj_name.split("_"):
            if not token:
                continue
            idx = part.rfind(token)
            if idx != -1:
                end = max(end, idx + len(token))
        if 0 < end < len(part):
            part = part[end:]
        return part

    @classmethod
    def _build_part_name(cls, base_name, obj_name, prefix, part_source):
        """去掉公共前缀与物体名标识后生成部位名称：与原名称相同则只保留部位名，否则拼接为“原名 部位名”"""
        base = cls._derive_part_name(base_name, obj_name, prefix)
        suffix = cls._derive_part_name(part_source, obj_name, prefix)
        if suffix and base and base != suffix:
            return f"{base} {suffix}"
        return suffix or base or base_name

    @staticmethod
    def _count_vertices_per_material(obj):
        """统计每个材质索引对应的唯一顶点数"""
        mesh = obj.data
        vert_sets = {}
        for poly in mesh.polygons:
            mat_idx = poly.material_index
            if mat_idx not in vert_sets:
                vert_sets[mat_idx] = set()
            for vi in poly.vertices:
                vert_sets[mat_idx].add(vi)
        return {idx: len(verts) for idx, verts in vert_sets.items()}

    @staticmethod
    def _add_armature(context, objs, source_obj):
        """为物体列表添加骨架修改器（从 source_obj 复制）"""
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objs:
            if obj.type == 'MESH':
                obj.select_set(True)
        context.view_layer.objects.active = source_obj

        armature_modifiers = [mod for mod in source_obj.modifiers if mod.type == 'ARMATURE']
        if armature_modifiers:
            src_mod = armature_modifiers[0]
            for obj in objs:
                if obj.type == 'MESH':
                    new_mod = obj.modifiers.new(name="Armature", type='ARMATURE')
                    new_mod.object = src_mod.object
                    new_mod.use_bone_envelopes = src_mod.use_bone_envelopes
                    new_mod.use_vertex_groups = src_mod.use_vertex_groups
                    new_mod.use_deform_preserve_volume = src_mod.use_deform_preserve_volume
                    new_mod.vertex_group = src_mod.vertex_group

    # ========== 合并模式 ==========

    def _execute_merge(self, context):
        active_e = context.active_object
        selected_others = [obj for obj in context.selected_objects if obj != active_e and obj.type == 'MESH']

        if not selected_others:
            self.report({'ERROR'}, "请选择除活动物体外的至少一个网格物体")
            return {'CANCELLED'}

        # 步骤1: 合并 A B C 到 A
        target_a = selected_others[0]
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_others:
            obj.select_set(True)
        context.view_layer.objects.active = target_a
        bpy.ops.object.join()

        # 步骤2: 匹配材质（按材质顶点数匹配，重命名A的材质，E使用A的材质）
        self._match_materials_merge(target_a, active_e)

        # 计算映射名称
        mapping_name = self._get_mapping_name(active_e.name)

        # 步骤3: 顶点组匹配重命名 (E为源, A为目标)
        bpy.ops.object.select_all(action='DESELECT')
        active_e.select_set(True)
        target_a.select_set(True)
        context.view_layer.objects.active = target_a
        try:
            bpy.ops.xqfa.vertex_groups_match_rename('EXEC_DEFAULT', mapping_name=mapping_name)
        except Exception as e:
            self.report({'WARNING'}, f"顶点组匹配重命名失败: {e}")

        # 步骤4: 形态键匹配重命名 (E为源, A为目标)
        if target_a.data.shape_keys and active_e.data.shape_keys:
            try:
                bpy.ops.xqfa.shape_keys_match_rename('EXEC_DEFAULT', mapping_name=mapping_name)
            except Exception as e:
                self.report({'WARNING'}, f"形态键匹配重命名失败: {e}")

        # 步骤5: 不执行名称排序

        # 步骤6: 按材质分离 A (使用材质名作为物体名)
        bpy.ops.object.select_all(action='DESELECT')
        target_a.select_set(True)
        context.view_layer.objects.active = target_a
        try:
            bpy.ops.xqfa.separate_by_material('EXEC_DEFAULT', naming_mode='MATERIAL')
        except Exception as e:
            self.report({'WARNING'}, f"按材质分离失败: {e}")

        separated_objs = context.selected_objects

        # 步骤7: 添加骨架
        self._add_armature(context, separated_objs, active_e)

        self.report({'INFO'}, "合并模式完成")
        return {'FINISHED'}

    def _match_materials_merge(self, obj_a, obj_e):
        """合并模式：按材质顶点数匹配A和E的材质，重命名A的材质，E使用A的材质"""
        # 统计A和E每个材质的顶点数
        a_mat_verts = self._count_vertices_per_material(obj_a)
        e_mat_verts = self._count_vertices_per_material(obj_e)

        # 先按顶点数匹配出成对的材质
        pairs = []  # (a_mat, e_mat, e_idx)
        used_e_indices = set()
        for a_idx, a_mat in enumerate(obj_a.data.materials):
            if a_mat is None:
                continue
            a_count = a_mat_verts.get(a_idx, 0)
            for e_idx, e_mat in enumerate(obj_e.data.materials):
                if e_mat is None or e_idx in used_e_indices:
                    continue
                e_count = e_mat_verts.get(e_idx, 0)
                if a_count == e_count and a_count > 0:
                    pairs.append((a_mat, e_mat, e_idx))
                    used_e_indices.add(e_idx)
                    break

        # 仅用参与匹配的E材质名计算公共前缀，避免其它无关材质名把前缀截断
        common_prefix = self._find_common_prefix([e_mat.name for _, e_mat, _ in pairs])

        # 重命名A的材质：去掉公共前缀，与E的部位名保持一致
        new_names = [self._build_part_name(a_mat.name, obj_e.name, common_prefix, e_mat.name)
                     for a_mat, e_mat, _ in pairs]
        for (a_mat, e_mat, e_idx), new_name in zip(pairs, new_names):
            a_mat.name = new_name
            # E的对应材质槽直接使用A的材质
            obj_e.material_slots[e_idx].material = a_mat

    # ========== 分离模式 ==========

    def _execute_separate(self, context):
        active_e = context.active_object
        selected_others = [obj for obj in context.selected_objects if obj != active_e and obj.type == 'MESH']

        if not selected_others:
            self.report({'ERROR'}, "请选择除活动物体外的至少一个网格物体")
            return {'CANCELLED'}

        # 计算映射名称前缀
        prefix = self._get_mapping_name(active_e.name)

        # 步骤1: 复制E为F，按材质分离F（此时物体名/材质名仍带完整前缀）
        bpy.ops.object.select_all(action='DESELECT')
        active_e.select_set(True)
        context.view_layer.objects.active = active_e
        bpy.ops.object.duplicate()
        obj_f = context.selected_objects[0]

        try:
            bpy.ops.xqfa.separate_by_material('EXEC_DEFAULT', naming_mode='MATERIAL')
        except Exception as e:
            self.report({'WARNING'}, f"按材质分离失败: {e}")
            return {'CANCELLED'}

        separated_e_objs = [obj for obj in context.selected_objects if obj.type == 'MESH']

        # 步骤2: 按物体顶点数匹配 A B C 和 分离物体
        others_vert_counts = {obj: len(obj.data.vertices) for obj in selected_others}
        matches = []  # (other_obj, sep_obj)
        used_sep = set()
        for other in selected_others:
            other_count = others_vert_counts[other]
            for sep_obj in separated_e_objs:
                if id(sep_obj) in used_sep:
                    continue
                if len(sep_obj.data.vertices) == other_count:
                    matches.append((other, sep_obj))
                    used_sep.add(id(sep_obj))
                    break

        # 步骤3: 仅用参与匹配的材质名计算公共前缀，避免其它无关材质名把前缀截断
        matched_mat_names = [sep_obj.data.materials[0].name
                             for _, sep_obj in matches if sep_obj.data.materials]
        common_prefix = self._find_common_prefix(matched_mat_names)
        print(f"[同步提取和解包|分离] 匹配材质: {matched_mat_names} 公共前缀: {common_prefix!r}")

        # 去除E材质名的公共前缀
        for mat in active_e.data.materials:
            if mat:
                mat.name = self._derive_part_name(mat.name, active_e.name, common_prefix) or mat.name

        # 步骤4: 处理每对匹配
        for other_obj, sep_obj in matches:
            # 分离物体与E共用材质数据块，用其材质名推导部位名
            sep_mat = sep_obj.data.materials[0] if sep_obj.data.materials else None
            sep_mat_name = sep_mat.name if sep_mat else sep_obj.name
            part_name = self._derive_part_name(sep_mat_name, active_e.name, common_prefix) or sep_mat_name

            # 重命名 other 的材质（去掉公共前缀后使用部位名），物体也同时添加后缀重命名
            for mat in other_obj.data.materials:
                if mat:
                    mat.name = self._build_part_name(mat.name, active_e.name, common_prefix, sep_mat_name)
            other_obj.name = f"{other_obj.name} {part_name}"

            # E物体的对应材质槽替换为 other 的对应材质
            if sep_mat is not None:
                for i in range(len(active_e.data.materials)):
                    if active_e.data.materials[i] is sep_mat:
                        if other_obj.data.materials and other_obj.data.materials[0]:
                            active_e.data.materials[i] = other_obj.data.materials[0]
                        break

            # 步骤4a: 顶点组匹配重命名 (sep_obj为源, other为目标)
            vg_mapping_name = prefix + part_name
            bpy.ops.object.select_all(action='DESELECT')
            sep_obj.select_set(True)
            other_obj.select_set(True)
            context.view_layer.objects.active = other_obj
            try:
                bpy.ops.xqfa.vertex_groups_match_rename('EXEC_DEFAULT', mapping_name=vg_mapping_name)
            except Exception as e:
                self.report({'WARNING'}, f"顶点组匹配重命名失败 ({part_name}): {e}")

            # 形态键匹配重命名
            if other_obj.data.shape_keys and sep_obj.data.shape_keys:
                sk_mapping_name = vg_mapping_name + "_形态键"
                try:
                    bpy.ops.xqfa.shape_keys_match_rename('EXEC_DEFAULT', mapping_name=sk_mapping_name)
                except Exception as e:
                    self.report({'WARNING'}, f"形态键匹配重命名失败 ({part_name}): {e}")

        # 步骤5: 不执行名称排序

        # 步骤6: 为 A B C 添加骨架
        self._add_armature(context, selected_others, active_e)

        # 清理临时分离物体
        bpy.ops.object.select_all(action='DESELECT')
        for sep_obj in separated_e_objs:
            sep_obj.select_set(True)
        bpy.ops.object.delete()

        self.report({'INFO'}, "分离模式完成")
        return {'FINISHED'}


def _srgb_byte_to_linear(byte_val):
    """sRGB 编码的字节值转场景线性值"""
    c = byte_val / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


# 预设颜色 #FF7500FF：RGB 经 sRGB→线性转换（颜色属性按线性空间读写），Alpha 为原始值
WW_COLOR_PRESET_LINEAR = (1.0, _srgb_byte_to_linear(0x75), 0.0, 1.0)


class XQFA_OT_WWAttributePreset(bpy.types.Operator):
    bl_idname = "xqfa.ww_attribute_preset"
    bl_label = "WW属性预设"
    bl_description = ("对选中物体应用WWMI属性预设：\n"
                      "1. 顶部添加TEXCOORD.xy~TEXCOORD3.xy四个UV（内容为原活动UV）\n"
                      "2. 活动UV与渲染UV设为TEXCOORD.xy\n"
                      "3. 调用平滑法线-八面体UV生成TEXCOORD1.xy\n"
                      "4. 调用视角投影UV将TEXCOORD3.xy按当前视角投影并缩放居中\n"
                      "5. 顶部添加面拐字节顶点色COLOR并填充#FF7500FF")
    bl_options = {'REGISTER', 'UNDO'}

    UV_PRESET_NAMES = ("TEXCOORD.xy", "TEXCOORD1.xy", "TEXCOORD2.xy", "TEXCOORD3.xy")
    COLOR_NAME = "COLOR"

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and len(context.selected_objects) > 0

    def execute(self, context):
        # 确保对象模式（网格数据编辑需在对象模式下进行）
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not meshes:
            self.report({'WARNING'}, "未选中任何网格物体")
            return {'CANCELLED'}

        # 步骤1+2: 顶部添加4个预设UV，并把活动/渲染UV设为TEXCOORD.xy
        uv_ready = []
        for obj in meshes:
            if self._prepend_uv_layers(obj):
                uv_ready.append(obj)

        # 视角投影UV到TEXCOORD3.xy（批量执行：多物体整体投影、等比缩放0.95并居中）
        # 须在八面体UV之前执行：八面体UV内部会把活动UV重设为索引0（TEXCOORD.xy），
        # 从而保证预设结束时活动UV仍为TEXCOORD.xy
        if uv_ready:
            try:
                with context.temp_override(active_object=uv_ready[0], selected_objects=uv_ready):
                    bpy.ops.xqfa.uv_project_from_view('EXEC_DEFAULT')
            except Exception as e:
                self.report({'WARNING'}, f"视角投影UV失败: {e}")

        # 调用八面体UV操作符生成TEXCOORD1.xy（对单个物体执行）
        octa_count = 0
        for obj in uv_ready:
            try:
                with context.temp_override(active_object=obj, selected_objects=[obj]):
                    bpy.ops.xqfa.octahedral_uv('EXEC_DEFAULT')
                octa_count += 1
            except Exception as e:
                self.report({'WARNING'}, f"物体 {obj.name} 八面体UV失败: {e}")

        # 步骤5: 顶部添加面拐字节顶点色COLOR
        color_count = 0
        for obj in meshes:
            try:
                self._prepend_color_attribute(obj.data)
                color_count += 1
            except Exception as e:
                self.report({'WARNING'}, f"物体 {obj.name} 添加COLOR失败: {e}")

        # 强制刷新所有区域
        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"WW属性预设完成: UV {len(uv_ready)}/{len(meshes)}, 八面体UV {octa_count}, COLOR {color_count}/{len(meshes)}")
        return {'FINISHED'}

    def _prepend_uv_layers(self, obj):
        """在UV列表顶部添加TEXCOORD.xy~TEXCOORD3.xy，并把活动/渲染UV设为TEXCOORD.xy

        独立实现的顶部插入逻辑（快照 -> 从后往前删除 -> 新建预设层 -> 重建原有层）。
        新增层的内容填充为原活动UV的数据。返回 True 表示UV已就绪（可做八面体UV计算）。
        """
        mesh = obj.data
        uv_layers = mesh.uv_layers

        if len(mesh.loops) == 0:
            self.report({'WARNING'}, f"物体 {obj.name} 没有面，已跳过")
            return False

        preset_names = set(self.UV_PRESET_NAMES)

        # 快照原有层（名称、渲染状态、UV数据），排除与预设同名的旧层，保证重复执行不产生.001副本
        original = []
        for l in uv_layers:
            if l.name in preset_names:
                continue
            flat = [0.0] * (len(l.data) * 2)
            l.data.foreach_get("uv", flat)
            original.append((l.name, l.active_render, flat))

        # Blender 每个网格最多 8 个 UV 贴图（MAX_MTFACE 限制）
        if len(original) + len(self.UV_PRESET_NAMES) > 8:
            self.report({'WARNING'}, f"物体 {obj.name} UV层数超限（非预设层已有 {len(original)} 个，还需 {len(self.UV_PRESET_NAMES)} 个），已跳过")
            return False

        # 快照填充源：原活动UV的数据（无活动层时取第一个层）
        src_layer = uv_layers.active
        if src_layer is None and len(uv_layers) > 0:
            src_layer = uv_layers[0]
        src_data = None
        if src_layer is not None:
            src_data = [0.0] * (len(src_layer.data) * 2)
            src_layer.data.foreach_get("uv", src_data)

        # 删除所有原有层（从后往前按索引删除，避免持有失效引用）
        for i in range(len(uv_layers) - 1, -1, -1):
            uv_layers.remove(uv_layers[i])

        # 顶部创建4个预设层并填充原活动UV数据
        for name in self.UV_PRESET_NAMES:
            layer = uv_layers.new(name=name)
            if layer is None:
                self.report({'WARNING'}, f"物体 {obj.name} 创建UV贴图失败：可能已达数量上限或网格没有面")
                return False
            if src_data:
                layer.data.foreach_set("uv", src_data)

        # 按原顺序重建原有层
        for name, render_flag, flat in original:
            layer = uv_layers.new(name=name)
            if layer is None:
                self.report({'WARNING'}, f"物体 {obj.name} 重建UV贴图 {name} 失败")
                return False
            if flat:
                layer.data.foreach_set("uv", flat)
            layer.active_render = render_flag

        # 活动UV与渲染UV都设为TEXCOORD.xy
        first = uv_layers[self.UV_PRESET_NAMES[0]]
        uv_layers.active = first
        for l in uv_layers:
            l.active_render = (l.name == self.UV_PRESET_NAMES[0])

        return True

    def _prepend_color_attribute(self, mesh):
        """在颜色属性列表顶部添加面拐字节顶点色COLOR，并填充预设颜色"""
        color_attrs = mesh.color_attributes

        # 记录原活动/渲染颜色属性名（用于恢复指向）
        active_name = color_attrs.active.name if color_attrs.active else None
        render_idx = color_attrs.render_color_index
        render_name = color_attrs[render_idx].name if 0 <= render_idx < len(color_attrs) else None

        # 快照现有颜色属性（同名COLOR的旧属性被预设覆盖，不参与重建）
        original = []
        for attr in color_attrs:
            if attr.name == self.COLOR_NAME:
                continue
            flat = [0.0] * (len(attr.data) * 4)
            attr.data.foreach_get("color", flat)
            original.append((attr.name, attr.domain, attr.data_type, flat))

        # 删除所有颜色属性（从后往前按索引删除，避免持有失效引用）
        for i in range(len(color_attrs) - 1, -1, -1):
            color_attrs.remove(color_attrs[i])

        # 顶部创建预设颜色属性并填充
        new_attr = color_attrs.new(name=self.COLOR_NAME, type='BYTE_COLOR', domain='CORNER')
        if new_attr is None:
            raise RuntimeError("创建颜色属性失败")
        fill = WW_COLOR_PRESET_LINEAR * len(new_attr.data)
        if fill:
            new_attr.data.foreach_set("color", fill)

        # 按原顺序重建原有属性
        for name, domain, dtype, flat in original:
            attr = color_attrs.new(name=name, type=dtype, domain=domain)
            if attr is None:
                raise RuntimeError(f"重建颜色属性 {name} 失败")
            if flat:
                attr.data.foreach_set("color", flat)

        # 恢复原活动/渲染颜色属性指向（若同名属性仍存在）
        for saved_name in (active_name, render_name):
            if not saved_name:
                continue
            target = next((a for a in color_attrs if a.name == saved_name), None)
            if target is None:
                continue
            color_attrs.active = target
            color_attrs.render_color_index = [a.name for a in color_attrs].index(target)


classes = (
    XQFA_PT_WWMI,
    XQFA_OT_SyncExtractUnpack,
    XQFA_OT_WWAttributePreset,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
