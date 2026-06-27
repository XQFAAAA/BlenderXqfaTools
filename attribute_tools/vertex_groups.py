# type: ignore
import bpy
import numpy as np
import time
from typing import Dict, Tuple, Set, List, Optional

class DATA_PT_vertex_group_tools(bpy.types.Panel):
    bl_label = "顶点组"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了此子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'AttributeTools'

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.operator(O_VertexGroupsCleanZeroWeight.bl_idname, text=O_VertexGroupsCleanZeroWeight.bl_label, icon="GROUP_VERTEX")
        col.operator(O_VertexGroupsDelNoneSelected.bl_idname, text=O_VertexGroupsDelNoneSelected.bl_label, icon="GROUP_VERTEX")
        col.operator(O_VertexGroupsDelAllSelected.bl_idname, text=O_VertexGroupsDelAllSelected.bl_label, icon="GROUP_VERTEX")

        col = layout.column(align=True)
        col.operator(O_VertexGroupsMatchRename.bl_idname, text=O_VertexGroupsMatchRename.bl_label, icon="SORTBYEXT")
        col.operator(O_VertexGroupsSortMatch.bl_idname, text=O_VertexGroupsSortMatch.bl_label, icon="SORTSIZE")

        self._draw_mappings(context)

    def _draw_mappings(self, context):
        scene = context.scene
        mappings = getattr(scene, 'xqfa_vertex_group_mappings', None)
        if mappings is None:
            return
        if len(mappings) == 0:
            return
        layout = self.layout
        layout.separator()
        box = layout.box()
        box.label(text="映射记录", icon="COLLAPSEMENU")
        for idx, item in enumerate(mappings):
            row = box.row(align=True)
            col_exp = row.column(align=True)
            sub = col_exp.row(align=True)
            icon = "TRIA_DOWN" if item.expanded else "TRIA_RIGHT"
            sub.prop(item, "expanded", icon=icon, icon_only=True, emboss=False)
            if not item.label:
                item.label = f"映射 {idx + 1}"
            sub.prop(item, "label", text="")
            sub.label(text=f"({len(item.pairs)}项)")
            col_btns = row.column(align=True)
            col_btns.alignment = 'RIGHT'
            btns = col_btns.row(align=True)
            op_lr = btns.operator(O_VertexGroupMappingApply.bl_idname, text="→")
            op_lr.index = idx
            op_lr.direction = "LEFT_TO_RIGHT"
            op_rl = btns.operator(O_VertexGroupMappingApply.bl_idname, text="←")
            op_rl.index = idx
            op_rl.direction = "RIGHT_TO_LEFT"
            op_l_order = btns.operator(O_VertexGroupMappingReorder.bl_idname, text="L↓")
            op_l_order.index = idx
            op_l_order.direction = "LEFT"
            op_r_order = btns.operator(O_VertexGroupMappingReorder.bl_idname, text="R↓")
            op_r_order.index = idx
            op_r_order.direction = "RIGHT"
            btns.operator(O_VertexGroupMappingRemove.bl_idname, text="", icon="X").index = idx
            if item.expanded:
                box.template_list(
                    "VGPairList",
                    f"vg_pairs_{idx}",
                    item,
                    "pairs",
                    item,
                    "active_pair_index",
                    type='DEFAULT',
                )


class XqfaVertexGroupPairItem(bpy.types.PropertyGroup):
    left_name: bpy.props.StringProperty(name="左")
    right_name: bpy.props.StringProperty(name="右")
    similarity: bpy.props.StringProperty(name="相似度", default="")


class XqfaVertexGroupMappingItem(bpy.types.PropertyGroup):
    expanded: bpy.props.BoolProperty(name="展开", default=False)
    label: bpy.props.StringProperty(name="标题")
    pairs: bpy.props.CollectionProperty(type=XqfaVertexGroupPairItem)
    active_pair_index: bpy.props.IntProperty(default=0)


class VGPairList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=item.left_name)
            row.label(text="↔")
            row.label(text=item.right_name)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="")


class O_VertexGroupMappingRemove(bpy.types.Operator):
    bl_idname = "xqfa.vertex_group_mapping_remove"
    bl_label = "关闭映射"
    bl_description = "从列表中移除此映射记录"

    index: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        mappings = getattr(scene, 'xqfa_vertex_group_mappings', None)
        if mappings is None:
            return {'CANCELLED'}
        if self.index < 0 or self.index >= len(mappings):
            return {'CANCELLED'}
        mappings.remove(self.index)
        return {'FINISHED'}


class O_VertexGroupMappingApply(bpy.types.Operator):
    bl_idname = "xqfa.vertex_group_mapping_apply"
    bl_label = "应用映射"
    bl_description = "按映射关系重命名选中物体的顶点组"

    index: bpy.props.IntProperty()
    direction: bpy.props.EnumProperty(
        name="方向",
        items=[
            ("LEFT_TO_RIGHT", "左→右", "用左物体的名称重命名右物体"),
            ("RIGHT_TO_LEFT", "右→左", "用右物体的原始名称重命名左物体"),
        ],
        default="LEFT_TO_RIGHT",
    )

    def execute(self, context):
        scene = context.scene
        mappings = getattr(scene, 'xqfa_vertex_group_mappings', None)
        if mappings is None or self.index < 0 or self.index >= len(mappings):
            return {'CANCELLED'}
        item = mappings[self.index]

        selected_objs = [o for o in context.selected_objects if o.type == 'MESH' and o.vertex_groups]
        if not selected_objs:
            self.report({'ERROR'}, "请先选择有顶点组的网格物体")
            return {'CANCELLED'}

        if self.direction == "LEFT_TO_RIGHT":
            lookup = [(p.left_name, p.right_name) for p in item.pairs]
        else:
            lookup = [(p.right_name, p.left_name) for p in item.pairs]

        total_renamed = 0
        total_skipped = 0
        affected_objs = 0

        for obj in selected_objs:
            vgs = obj.vertex_groups
            obj_renamed = 0
            for old_name, new_name in lookup:
                vg = vgs.get(old_name)
                if vg is None:
                    total_skipped += 1
                    continue
                try:
                    vg.name = new_name
                    obj_renamed += 1
                except Exception:
                    total_skipped += 1
            if obj_renamed > 0:
                total_renamed += obj_renamed
                affected_objs += 1

        self.report({'INFO'}, f"影响 {affected_objs}/{len(selected_objs)} 个物体：已重命名 {total_renamed} 项，跳过 {total_skipped} 项")
        return {'FINISHED'}


class O_VertexGroupMappingReorder(bpy.types.Operator):
    bl_idname = "xqfa.vertex_group_mapping_reorder"
    bl_label = "按映射顺序重排顶点组"
    bl_description = "按映射记录中左侧（或右侧）名称的顺序，重排活动物体顶点组（保留权重，缺失项放到末尾）"

    index: bpy.props.IntProperty()
    direction: bpy.props.EnumProperty(
        name="顺序来源",
        items=[
            ("LEFT", "应用左侧顺序", "按映射中 left_name 的出现顺序排列"),
            ("RIGHT", "应用右侧顺序", "按映射中 right_name 的出现顺序排列"),
        ],
        default="LEFT",
    )

    def execute(self, context):
        scene = context.scene
        mappings = getattr(scene, 'xqfa_vertex_group_mappings', None)
        if mappings is None or self.index < 0 or self.index >= len(mappings):
            return {'CANCELLED'}

        item = mappings[self.index]
        if not item.pairs:
            self.report({'WARNING'}, "此映射记录为空")
            return {'CANCELLED'}

        target_objs = [o for o in context.selected_objects if o.type == 'MESH']
        if not target_objs:
            self.report({'ERROR'}, "请先选择网格物体")
            return {'CANCELLED'}

        desired_names = [p.left_name if self.direction == "LEFT" else p.right_name for p in item.pairs]

        total_matched = 0
        total_added = 0
        total_extra = 0
        for obj in target_objs:
            result = self._reorder_vertex_groups(obj, desired_names)
            total_matched += result['matched']
            total_added += result['added']
            total_extra += result['extra']

        self.report(
            {'INFO'},
            f"已在 {len(target_objs)} 个物体上调整顺序 (共 {total_matched} 匹配, {total_added} 新建空组, {total_extra} 保留到末尾)"
        )
        return {'FINISHED'}

    def _reorder_vertex_groups(self, target_obj: bpy.types.Object, desired_order: List[str]) -> Dict[str, any]:
        """按 desired_order 顺序重排顶点组（备份-清空-重建，未在 desired_order 中的组放到末尾）"""
        target_vgs = target_obj.vertex_groups
        mesh = target_obj.data

        weight_data: Dict[str, Dict[int, float]] = {}
        original_names = [vg.name for vg in target_vgs]

        for vert in mesh.vertices:
            for group in vert.groups:
                vg_name = original_names[group.group]
                if group.weight > 0:
                    if vg_name not in weight_data:
                        weight_data[vg_name] = {}
                    weight_data[vg_name][vert.index] = group.weight

        for i in range(len(target_vgs) - 1, -1, -1):
            target_vgs.remove(target_vgs[i])

        matched_count = 0
        added_count = 0
        used_names: Set[str] = set()

        for name in desired_order:
            if name in used_names:
                continue
            used_names.add(name)

            new_vg = target_vgs.new(name=name)
            if name in weight_data:
                vg_weights = weight_data.pop(name)
                for vert_index, weight in vg_weights.items():
                    new_vg.add([vert_index], weight, 'REPLACE')
                matched_count += 1
            else:
                added_count += 1

        extra_count = 0
        for extra_name in list(weight_data.keys()):
            if extra_name in used_names:
                extra_count += 1
                continue
            used_names.add(extra_name)
            new_vg = target_vgs.new(name=extra_name)
            vg_weights = weight_data.pop(extra_name)
            for vert_index, weight in vg_weights.items():
                new_vg.add([vert_index], weight, 'REPLACE')
            extra_count += 1

        return {
            'matched': matched_count,
            'added': added_count,
            'extra': extra_count,
            'original_total': len(original_names),
            'order_total': len(desired_order),
        }


class O_VertexGroupsDelAllSelected(bpy.types.Operator):
    bl_idname = "xqfa.vertex_groups_del_all_more"
    bl_label = "批量删除所有顶点组"
    bl_description = "删除选择物体的所有顶点组"

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=160)

    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                for group in obj.vertex_groups:
                    obj.vertex_groups.remove(group)
                obj.update_tag()
            else:
                print("不是网格对象")
        self.report({'INFO'}, "已删除选择物体的所有顶点组！")
        return {'FINISHED'}


class O_VertexGroupsCleanZeroWeight(bpy.types.Operator):
    """清理选中物体中顶点组的零权重"""
    bl_idname = "xqfa.vertex_groups_clean_zero_weight"
    bl_label = "批量清理零权重"
    bl_description = "对所有选中的网格物体清理顶点组中的零权重"
    bl_options = {'REGISTER', 'UNDO'}

    weight_limit: bpy.props.FloatProperty(
        name="权重阈值",
        description="低于此值的权重将被清理",
        default=0.01,
        min=0.0,
        max=1.0,
        step=0.01,
        precision=3,
    )

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and any(obj.type == 'MESH' for obj in context.selected_objects)

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=200)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "weight_limit")

    def execute(self, context):
        cleaned_count = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH' or not obj.vertex_groups:
                continue
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.vertex_group_clean(group_select_mode='ALL', limit=self.weight_limit)
            cleaned_count += 1

        if cleaned_count > 0:
            self.report({'INFO'}, f"已清理 {cleaned_count} 个物体的零权重")
        else:
            self.report({'INFO'}, "未找到需要清理的物体")
        return {'FINISHED'}


class O_VertexGroupsDelNoneSelected(bpy.types.Operator):
    bl_idname = "xqfa.vertex_groups_del_none_more"
    bl_label = "批量删除空顶点组"
    bl_description = "删除选择物体中没有顶点的顶点组"

    def execute(self, context):
        total_removed = 0
        removed_names = []
        for obj in context.selected_objects:
            if obj and obj.type == 'MESH':
                vertex_groups = obj.vertex_groups
                mesh = obj.data

                vertex_group_info = {}
                for group in vertex_groups:
                    vertex_group_info[group.name] = []

                for vertex in mesh.vertices:
                    for group in vertex.groups:
                        group_index = group.group
                        group_name = vertex_groups[group_index].name
                        weight = group.weight
                        vertex_group_info[group_name].append((vertex.index, weight))

                for group_name, vertex_info in vertex_group_info.items():
                    if not vertex_info:
                        obj.vertex_groups.remove(obj.vertex_groups[group_name])
                        removed_names.append(f"[{obj.name}] {group_name}")
                        total_removed += 1

        if total_removed > 0:
            detail = "; ".join(removed_names)
            self.report({'INFO'}, f"已删除 {total_removed} 个无权重顶点组: {detail}")
        else:
            self.report({'INFO'}, "未找到需要删除的无权重顶点组")
        return {'FINISHED'}


# ----------------------------------------------------------------
# 3. 匹配重命名操作 (Match Rename Operator) - 💥 优化
# ----------------------------------------------------------------
class O_VertexGroupsMatchRename(bpy.types.Operator):
    """选择物体的顶点组名称-->活动物体的顶点组名称，按顶点平均位置匹配"""
    bl_idname = "xqfa.vertex_groups_match_rename"
    bl_label = "顶点组名称匹配重命名"

    similarity_threshold: bpy.props.FloatProperty(
        name="相似度",
        description="匹配顶点组时的最小相似度(0-1)",
        default=0.94,
        min=0.9,
        max=1.0,
        step=0.01,
        precision=3
    )

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=200)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "similarity_threshold")

    def execute(self, context: bpy.types.Context) -> Set[str]:
        """主执行函数"""
        start_time = time.time()

        try:
            obj_a, obj_b = self._validate_input(context)

            centers_a = self._get_vertex_group_centers(obj_a)
            centers_b = self._get_vertex_group_centers(obj_b)

            if not centers_a:
                raise Exception(f"源物体 ({obj_a.name}) 没有非空顶点组")
            if not centers_b:
                raise Exception(f"目标物体 ({obj_b.name}) 没有非空顶点组")

            result = self._rename_matching_vertex_groups(obj_a, obj_b, centers_a, centers_b)

            self._print_detailed_results(obj_a, obj_b, result)

            self._store_mapping(context, result)

            elapsed_time = time.time() - start_time
            time_msg = f"总耗时: {elapsed_time:.4f}秒"

            if result['renamed_count'] > 0:
                self.report({'INFO'}, f"成功匹配重命名 {result['renamed_count']} 个顶点组 ({time_msg})")
            else:
                self.report({'WARNING'}, f"没有找到匹配的顶点组 ({time_msg})")

            return {'FINISHED'}

        except Exception as e:
            elapsed_time = time.time() - start_time
            self.report({'ERROR'}, f"{str(e)} (耗时: {elapsed_time:.4f}秒)")
            return {'CANCELLED'}

    def _store_mapping(self, context, result):
        scene = context.scene
        if not hasattr(scene, 'xqfa_vertex_group_mappings'):
            return
        mappings = scene.xqfa_vertex_group_mappings
        item = mappings.add()
        item.label = f"映射 {len(mappings)}"
        item.expanded = False
        pair_items = result.get('pair_items', [])
        for left_name, right_name, similarity in pair_items:
            p = item.pairs.add()
            p.left_name = left_name
            p.right_name = right_name
            p.similarity = similarity
    
    def _validate_input(self, context: bpy.types.Context) -> Tuple[bpy.types.Object, bpy.types.Object]:
        """验证输入并返回两个网格物体"""
        selected_objs = context.selected_objects
        active_obj = context.active_object
        
        # 验证选择数量
        if len(selected_objs) != 2:
            raise ValueError("请选择2个网格物体")
            
        # 验证活动物体
        if active_obj not in selected_objs:
            raise ValueError("活动物体必须是选中的物体之一")
            
        # 获取两个物体
        # A物体: 源（提供名称的）
        # B物体: 目标（被重命名的，活动物体）
        obj_b = active_obj
        obj_a = next(obj for obj in selected_objs if obj != active_obj)
        
        # 验证物体类型
        if obj_a.type != 'MESH' or obj_b.type != 'MESH':
            raise ValueError("两个物体都必须是网格类型")
            
        # 验证模式 (重要：需要对象模式才能获取正确的矩阵和数据)
        if context.mode != 'OBJECT':
             raise ValueError("请切换到对象模式 (Object Mode) 以确保计算准确性")
            
        return obj_a, obj_b
    
    def _get_vertex_group_centers(self, obj: bpy.types.Object) -> Dict[str, np.ndarray]:
        """
        优化：向量化获取每个顶点组的中心位置（平均位置）。
        1. 获取所有顶点的全局坐标 (co * matrix_world)
        2. 获取所有顶点的所有顶点组权重（Blender API 相对高效的方式）
        3. 利用 NumPy 广播和求和计算加权平均中心点。
        """
        centers: Dict[str, np.ndarray] = {}
        mesh = obj.data
        
        if not obj.vertex_groups:
            return centers

        # 1. 获取所有顶点的全局坐标
        num_verts = len(mesh.vertices)
        verts_co = np.zeros((num_verts, 3))
        mesh.vertices.foreach_get('co', verts_co.ravel())
        
        matrix = np.array(obj.matrix_world)
        # 将局部坐标转换为全局坐标：V_global = V_local @ R.T + T
        global_verts = verts_co @ matrix[:3, :3].T + matrix[:3, 3]

        # 2. 获取所有顶点组的名称和索引映射
        vg_names = [vg.name for vg in obj.vertex_groups]
        vg_map = {name: i for i, name in enumerate(vg_names)}
        
        # 3. 获取所有顶点组的权重。
        # 使用 bmesh 或 foreach_get 无法直接高效获取所有顶点的所有权重。
        # 仍需遍历顶点，但可以批量处理，原始方法已是常见高效做法。
        # 为了进一步优化，我们直接从 Blender 的权重 API 获取并转换为 NumPy 矩阵。
        
        # 创建一个 Num_Verts x Num_Groups 的稀疏矩阵来存储权重 (如果大部分权重为0)
        # 但为了简单和通用性，我们先用一个稠密列表/字典来处理非零权重
        
        # 存储每个顶点组的 (总加权位置, 总权重)
        vg_data: Dict[str, Tuple[np.ndarray, float]] = {name: (np.zeros(3), 0.0) for name in vg_names}
        
        # 遍历所有顶点及其权重，计算加权和
        for i, vertex in enumerate(mesh.vertices):
            co = global_verts[i]
            for group in vertex.groups:
                group_index = group.group
                weight = group.weight
                
                if weight > 0:
                    group_name = obj.vertex_groups[group_index].name
                    
                    # 使用 NumPy 数组进行加法
                    current_sum, current_weight = vg_data[group_name]
                    vg_data[group_name] = (current_sum + co * weight, current_weight + weight)

        # 4. 计算平均中心点
        for name, (weighted_sum, total_weight) in vg_data.items():
            if total_weight > 0:
                # 平均位置 = 总加权位置 / 总权重
                centers[name] = weighted_sum / total_weight
                
        return centers

    def _calculate_similarity_vectorized(self, centers_a: Dict[str, np.ndarray], centers_b: Dict[str, np.ndarray], threshold: float) -> Tuple[List[Tuple[str, Optional[str], str]], int, int]:
        """
        优化: 向量化计算相似度矩阵并寻找最佳匹配。
        A: 源 (名称来源)
        B: 目标 (被重命名)
        """
        # 1. 准备数据：转换为 NumPy 数组
        a_names = list(centers_a.keys())
        b_names = list(centers_b.keys())
        a_centers = np.array(list(centers_a.values())) # N_a x 3
        b_centers = np.array(list(centers_b.values())) # N_b x 3
        
        if a_centers.size == 0 or b_centers.size == 0:
             return [], 0, 0
        
        # 2. 向量化计算所有距离 (欧几里得距离)
        # 使用 NumPy 广播计算距离：Distance Matrix M (N_b x N_a)
        # M[i, j] = ||b_centers[i] - a_centers[j]||
        
        # b_centers (N_b x 3)
        # a_centers (N_a x 3)
        
        # (b_i - a_j)^2 = b_i^2 - 2*b_i*a_j + a_j^2
        b_sq = np.sum(b_centers**2, axis=1, keepdims=True)  # N_b x 1
        a_sq = np.sum(a_centers**2, axis=1, keepdims=True).T # 1 x N_a
        
        # 2 * b_i * a_j
        b_dot_a = b_centers @ a_centers.T # N_b x N_a
        
        # 距离的平方
        dist_sq = b_sq - 2 * b_dot_a + a_sq
        # 避免浮点误差导致的微小负数
        dist_sq = np.maximum(dist_sq, 0)
        distances = np.sqrt(dist_sq) # N_b x N_a
        
        # 3. 将距离转换为相似度 (相似度 = 1 / (1 + 距离))
        similarity_matrix = 1.0 / (1.0 + distances) # N_b x N_a
        
        # 4. 寻找最佳匹配（贪婪匹配）
        renamed_count = 0
        matched_a_indices: Set[int] = set() # 已匹配的 A 组的索引
        matches: List[Tuple[str, Optional[str], str]] = []

        # 遍历 B 组 (目标组)
        for i, b_name in enumerate(b_names):
            best_match_index = -1
            best_similarity = 0.0
            
            # 获取 B 组 i 与所有 A 组的相似度行向量
            sim_row = similarity_matrix[i, :]

            # 寻找满足阈值的最佳匹配 A 组
            for j, a_name in enumerate(a_names):
                if j in matched_a_indices:
                    continue # 跳过已匹配的 A 组
                    
                similarity = sim_row[j]
                
                if similarity > best_similarity and similarity >= threshold:
                    best_similarity = similarity
                    best_match_index = j
            
            # 记录结果
            if best_match_index != -1:
                a_name = a_names[best_match_index]
                matched_a_indices.add(best_match_index) # 标记 A 组已使用
                renamed_count += 1
                matches.append((b_name, a_name, f"{best_similarity:.3f}"))
            else:
                matches.append((b_name, None, "no match"))
        
        return matches, len(a_names), len(b_names)

    def _rename_matching_vertex_groups(self,
                                     obj_a: bpy.types.Object,
                                     obj_b: bpy.types.Object,
                                     centers_a: Dict[str, np.ndarray],
                                     centers_b: Dict[str, np.ndarray]) -> Dict[str, any]:
        """匹配并重命名顶点组 (使用向量化匹配)"""

        matches, total_a, total_b = self._calculate_similarity_vectorized(
            centers_a,
            centers_b,
            self.similarity_threshold
        )

        match_lookup: Dict[str, Tuple[Optional[str], str]] = {b_name: (a_name, sim) for b_name, a_name, sim in matches}

        original_vg_names = [vg.name for vg in obj_b.vertex_groups]
        renamed_count = 0
        pair_items: List[Tuple[str, str, str]] = []

        for orig_name in original_vg_names:
            match_info = match_lookup.get(orig_name, (None, "-"))
            a_name, similarity_str = match_info
            if a_name:
                obj_b.vertex_groups[orig_name].name = a_name
                pair_items.append((orig_name, a_name, similarity_str))
                renamed_count += 1
            else:
                pair_items.append((orig_name, orig_name, similarity_str))

        return {
            'renamed_count': renamed_count,
            'matches': matches,
            'pair_items': pair_items,
            'total_a': total_a,
            'total_b': total_b
        }
    
    def _print_detailed_results(self,
                              obj_a: bpy.types.Object,
                              obj_b: bpy.types.Object,
                              result: Dict[str, any]) -> None:
        """打印详细结果到控制台"""
        header = f"顶点组匹配与重命名详细结果 (源A: {obj_a.name}, 目标B: {obj_b.name})"
        separator = "=" * len(header)

        print(f"\n{separator}")
        print(header)
        print(separator)
        print(f"相似度阈值: {self.similarity_threshold:.3f}")
        print(f"{'B物体原始名称':<30} {'重命名为':<30} {'相似度':<20}")
        print("-" * 80)

        matched = 0
        unmatched = 0

        for left_name, right_name, similarity_str in result['pair_items']:
            if left_name != right_name:
                matched += 1
                print(f"{left_name:<30} → {right_name:<30} {similarity_str:<20}")
            else:
                unmatched += 1
                print(f"{left_name:<30} → {'保留原名称':<30} {similarity_str:<20}")

        print(separator)
        print("总结:")
        print(f"  源A物体非空顶点组数量: {result['total_a']}")
        print(f"  目标B物体非空顶点组数量: {result['total_b']}")
        print(f"  匹配数量: {matched}")
        print(f"  未匹配数量: {unmatched}")
        print(f"  总重命名数量: {result['renamed_count']}")
        print(separator)


class O_VertexGroupsSortMatch(bpy.types.Operator):
    """活动物体的顶点组顺序-->选择物体的顶点组顺序"""
    bl_idname = "xqfa.vertex_groups_sort_match"
    bl_label = "顶点组顺序复制到选定项"

    def execute(self, context):
        start_time = time.time()  # 记录开始时间

        try:
            selected_objs = context.selected_objects
            active_obj = context.active_object

            # 验证选择
            if active_obj is None or active_obj not in selected_objs:
                raise ValueError("请确保活动物体在选中物体中")

            if len(selected_objs) < 2:
                raise ValueError("请至少选择2个网格物体")

            source_obj = active_obj
            target_objs = [obj for obj in selected_objs if obj != active_obj]

            if source_obj.type != 'MESH':
                raise ValueError("活动物体必须是网格类型")

            non_mesh = [obj.name for obj in target_objs if obj.type != 'MESH']
            if non_mesh:
                raise ValueError(f"以下目标物体不是网格类型: {', '.join(non_mesh)}")

            # 确保处于对象模式以操作顶点组
            if context.mode != 'OBJECT':
                 raise ValueError("请切换到对象模式 (Object Mode)")

            # 对每个目标物体执行排序
            total_matched = 0
            total_added = 0
            for target_obj in target_objs:
                result = self._sort_vertex_groups_optimized(target_obj, source_obj)
                total_matched += result['matched']
                total_added += result['added']
                self._print_detailed_results(source_obj, target_obj, result)

            # 计算总耗时
            elapsed_time = time.time() - start_time
            time_msg = f"总耗时: {elapsed_time:.4f}秒"

            self.report({'INFO'},
                       f"排序完成: {len(target_objs)}个目标物体, 匹配 {total_matched}个, 新建 {total_added}个 ({time_msg})")

            return {'FINISHED'}

        except Exception as e:
            elapsed_time = time.time() - start_time
            self.report({'ERROR'}, f"{str(e)} (耗时: {elapsed_time:.4f}秒)")
            return {'CANCELLED'}
    
    def _sort_vertex_groups_optimized(self, target_obj: bpy.types.Object, source_obj: bpy.types.Object) -> Dict[str, any]:
        """
        优化后的顶点组排序算法。
        1. 备份目标物体的所有权重数据。
        2. 清空目标物体的所有顶点组。
        3. 按照源物体的顺序，重建顶点组并恢复权重。
        """
        
        target_vgs = target_obj.vertex_groups
        source_vgs = source_obj.vertex_groups
        
        # 1. 备份目标物体的权重数据
        weight_data: Dict[str, Dict[int, float]] = {}
        original_vg_names = [vg.name for vg in target_vgs]
        
        mesh = target_obj.data
        
        # 遍历所有顶点，收集它们的权重
        for vert in mesh.vertices:
            for group in vert.groups:
                vg_name = original_vg_names[group.group]
                if group.weight > 0:
                    if vg_name not in weight_data:
                        weight_data[vg_name] = {}
                    # 存储 (顶点索引: 权重)
                    weight_data[vg_name][vert.index] = group.weight

        # 2. 清空目标物体的所有顶点组
        for i in range(len(target_vgs) - 1, -1, -1):
            target_vgs.remove(target_vgs[i])
            
        final_list: List[Tuple[str, str]] = [] # (最终名称, 状态)
        matched_count = 0
        added_count = 0
        
        # 3. 按照源物体的顺序，重建顶点组
        for desired_index, src_vg in enumerate(source_vgs):
            new_vg = target_vgs.new(name=src_vg.name)
            
            # 恢复权重（如果备份数据中存在）
            if src_vg.name in weight_data:
                vg_weights = weight_data.pop(src_vg.name)
                
                # 批量设置权重
                for vert_index, weight in vg_weights.items():
                    new_vg.add([vert_index], weight, 'REPLACE')
                
                matched_count += 1
                final_list.append((src_vg.name, '已匹配/移动'))
            else:
                added_count += 1
                final_list.append((src_vg.name, '新建空组'))
                
        # 4. 处理多余的顶点组
        extra_count = 0
        for extra_name, vg_weights in weight_data.items():
            new_vg = target_vgs.new(name=extra_name)
            
            # 恢复权重
            for vert_index, weight in vg_weights.items():
                new_vg.add([vert_index], weight, 'REPLACE')
            
            extra_count += 1
            final_list.append((extra_name, '多余/保留'))
            
        return {
            'matched': matched_count,
            'added': added_count,
            'extra': extra_count,
            'original_total': len(original_vg_names),
            'source_total': len(source_vgs),
            'final_list': final_list
        }

    def _print_detailed_results(self, 
                              source_obj: bpy.types.Object, 
                              target_obj: bpy.types.Object, 
                              result: Dict[str, any]) -> None:
        """打印详细结果到控制台"""
        header = f"顶点组排序详细结果 (源A: {source_obj.name}, 目标B: {target_obj.name})"
        separator = "=" * len(header)
        
        print(f"\n{separator}")
        print(header)
        print(separator)
        print(f"{'序号':<5} {'顶点组名称':<30} {'操作状态':<20}")
        print("-" * 55)
        
        # 打印排序后的最终列表
        for i, (name, status) in enumerate(result['final_list']):
            print(f"{i+1:<5} {name:<30} {status:<20}")

        
        print(separator)
        print("总结:")
        print(f"  源A物体顶点组数量: {result['source_total']}")
        print(f"  目标B物体原始数量: {result['original_total']}")
        print("-" * 15)
        print(f"  已匹配并移动数量: {result['matched']}")
        print(f"  新建空组数量: {result['added']}")
        print(f"  多余并保留数量: {result['extra']}")
        print(f"  最终顶点组总数: {len(result['final_list'])}")
        print(separator)



def register():
    bpy.utils.register_class(DATA_PT_vertex_group_tools)
    bpy.utils.register_class(XqfaVertexGroupPairItem)
    bpy.utils.register_class(XqfaVertexGroupMappingItem)
    bpy.utils.register_class(VGPairList)
    bpy.utils.register_class(O_VertexGroupMappingRemove)
    bpy.utils.register_class(O_VertexGroupMappingApply)
    bpy.utils.register_class(O_VertexGroupMappingReorder)
    bpy.utils.register_class(O_VertexGroupsDelAllSelected)
    bpy.utils.register_class(O_VertexGroupsCleanZeroWeight)
    bpy.utils.register_class(O_VertexGroupsDelNoneSelected)
    bpy.utils.register_class(O_VertexGroupsMatchRename)
    bpy.utils.register_class(O_VertexGroupsSortMatch)
    bpy.types.Scene.xqfa_vertex_group_mappings = bpy.props.CollectionProperty(type=XqfaVertexGroupMappingItem)

def unregister():
    if hasattr(bpy.types.Scene, 'xqfa_vertex_group_mappings'):
        del bpy.types.Scene.xqfa_vertex_group_mappings
    bpy.utils.unregister_class(DATA_PT_vertex_group_tools)
    bpy.utils.unregister_class(XqfaVertexGroupPairItem)
    bpy.utils.unregister_class(XqfaVertexGroupMappingItem)
    bpy.utils.unregister_class(VGPairList)
    bpy.utils.unregister_class(O_VertexGroupMappingRemove)
    bpy.utils.unregister_class(O_VertexGroupMappingApply)
    bpy.utils.unregister_class(O_VertexGroupMappingReorder)
    bpy.utils.unregister_class(O_VertexGroupsDelAllSelected)
    bpy.utils.unregister_class(O_VertexGroupsCleanZeroWeight)
    bpy.utils.unregister_class(O_VertexGroupsDelNoneSelected)
    bpy.utils.unregister_class(O_VertexGroupsMatchRename)
    bpy.utils.unregister_class(O_VertexGroupsSortMatch)
