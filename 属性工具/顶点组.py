# type: ignore
import bpy
import numpy as np
import time
from typing import Dict, Tuple, Set, List, Optional

class DATA_PT_vertex_group_tools(bpy.types.Panel):
    bl_label = "顶点组"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XBone'

    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了此子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'AttributeTools'

    def draw(self, context):
        layout = self.layout

        obj = context.object
        # 添加安全检查，确保物体存在且是网格物体
        if obj is None or obj.type != 'MESH':
            layout.label(text="请选择一个网格物体")
            return
        count0 = len(obj.vertex_groups)
        
        # 获取存储的统计信息，如果没有则显示默认值
        stats = obj.get("vertex_group_stats", {
            "total": count0,
            "with_weight": "N/A",
            "zero_weight": "N/A"
        })
        
        col = layout.column(align=True)
        row = col.row(align=True)
        row.label(text=f"数量: {stats['total']}")
        row.label(text=f"有权重: {stats['with_weight']}")
        row.label(text=f"无权重: {stats['zero_weight']}")

        row = col.row(align=True)
        row.operator(O_VertexGroupsCount.bl_idname, text=O_VertexGroupsCount.bl_label, icon="GROUP_VERTEX")
        row.operator(O_VertexGroupsDelNoneActive.bl_idname, text=O_VertexGroupsDelNoneActive.bl_label, icon="GROUP_VERTEX")

        row = col.row(align=True)
        row.prop(context.scene, "similarity_threshold")
        row.operator(O_VertexGroupsMatchRename.bl_idname, text=O_VertexGroupsMatchRename.bl_label, icon="SORTBYEXT")
        row.separator()  # 添加分割线
        row.operator(O_VertexGroupsSortMatch.bl_idname, text=O_VertexGroupsSortMatch.bl_label, icon="SORTSIZE")


class O_VertexGroupsCount(bpy.types.Operator):
    bl_idname = "xbone.vertex_groups_count"
    bl_label = "统计有无权重数量"
    bl_description = "统计活动物体顶点组中有权重和无权重的数量"
    
    def execute(self, context):
        obj = context.active_object
        if obj and obj.type == 'MESH':
            vertex_groups = obj.vertex_groups
            mesh = obj.data
            
            # 使用更高效的方法检查顶点组是否有权重
            count_with_weight = 0
            count_zero_weight = 0
            
            # 为每个顶点组创建一个标记，初始为False(无权重)
            has_weights = [False] * len(vertex_groups)
            
            # 遍历所有顶点
            for vertex in mesh.vertices:
                for group in vertex.groups:
                    group_index = group.group
                    # 如果找到至少一个顶点有该组的权重，标记为True
                    if group.weight > 0:
                        has_weights[group_index] = True
            
            # 统计结果
            for has_weight in has_weights:
                if has_weight:
                    count_with_weight += 1
            count_zero_weight = len(vertex_groups) - count_with_weight
            
            # 将结果存储在对象属性中
            obj["vertex_group_stats"] = {
                "total": len(vertex_groups),
                "with_weight": count_with_weight,
                "zero_weight": count_zero_weight
            }
            
            self.report({'INFO'}, f"统计完成: 总数 {len(vertex_groups)}, 有权重 {count_with_weight}, 无权重 {count_zero_weight}")
        else:
            self.report({'ERROR'}, "请先选择一个Mesh对象作为活动对象。")
            return {'CANCELLED'}

        return {'FINISHED'}


class O_VertexGroupsDelNoneActive(bpy.types.Operator):
    bl_idname = "xbone.vertex_groups_del_none_active"
    bl_label = "删除无权重顶点组"
    bl_description = "删除活动物体中没有顶点权重的顶点组"
    
    def execute(self, context):
        obj = context.active_object
        if obj and obj.type == 'MESH':
            vertex_groups = obj.vertex_groups
            mesh = obj.data
            
            # 使用更高效的方法检查顶点组是否有权重
            has_weights = [False] * len(vertex_groups)
            
            # 遍历所有顶点
            for vertex in mesh.vertices:
                for group in vertex.groups:
                    group_index = group.group
                    if group.weight > 0:
                        has_weights[group_index] = True
            
            # 收集要删除的顶点组名称（逆序以便安全删除）
            groups_to_remove = []
            for i, has_weight in reversed(list(enumerate(has_weights))):
                if not has_weight:
                    groups_to_remove.append(vertex_groups[i].name)
            
            # 删除无权重顶点组
            for group_name in groups_to_remove:
                vertex_groups.remove(vertex_groups[group_name])
            
            # 更新统计信息
            if "vertex_group_stats" in obj:
                remaining_count = len(vertex_groups)
                obj["vertex_group_stats"] = {
                    "total": remaining_count,
                    "with_weight": remaining_count,  # 删除后剩下的都是有权重的
                    "zero_weight": 0
                }
            
            self.report({'INFO'}, f"已删除 {len(groups_to_remove)} 个无权重顶点组：{groups_to_remove}")
        else:
            self.report({'ERROR'}, "请先选择一个Mesh对象作为活动对象。")
            return {'CANCELLED'}

        return {'FINISHED'}

# ----------------------------------------------------------------
# 3. 匹配重命名操作 (Match Rename Operator) - 💥 优化
# ----------------------------------------------------------------
class O_VertexGroupsMatchRename(bpy.types.Operator):
    bl_idname = "xbone.vertex_groups_match_rename"
    bl_label = "匹配重命名"
    bl_description = ("基于顶点平均位置匹配重命名活动物体的顶点组（需选择2个网格物体）\n"
                     "我用来给鸣潮提取的模型按解包的模型骨骼重命名，这样顶点组有名称意义也可以操控")
    
    def execute(self, context: bpy.types.Context) -> Set[str]:
        self.similarity_threshold = context.scene.similarity_threshold
        """主执行函数"""
        start_time = time.time()  # 记录开始时间
        
        try:
            # 验证输入并获取目标物体
            obj_a, obj_b = self._validate_input(context)
            
            # 执行匹配重命名并获取详细结果
            # 优化: 只需要计算一次中心点
            centers_a = self._get_vertex_group_centers(obj_a)
            centers_b = self._get_vertex_group_centers(obj_b)

            if not centers_a:
                raise Exception(f"源物体 ({obj_a.name}) 没有非空顶点组")
            if not centers_b:
                raise Exception(f"目标物体 ({obj_b.name}) 没有非空顶点组")

            result = self._rename_matching_vertex_groups(obj_a, obj_b, centers_a, centers_b)
            
            # 打印详细结果到控制台
            self._print_detailed_results(obj_a, obj_b, result)
            
            # 计算总耗时
            elapsed_time = time.time() - start_time
            time_msg = f"总耗时: {elapsed_time:.4f}秒" # 增加精度
            
            # 根据结果返回适当的消息
            if result['renamed_count'] > 0:
                self.report({'INFO'}, f"成功匹配重命名 {result['renamed_count']} 个顶点组 ({time_msg})")
            else:
                self.report({'WARNING'}, f"没有找到匹配的顶点组 ({time_msg})")
                
            return {'FINISHED'}
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            self.report({'ERROR'}, f"{str(e)} (耗时: {elapsed_time:.4f}秒)")
            return {'CANCELLED'}
    
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
        
        renamed_count = 0
        
        # 执行重命名
        for b_name, a_name, similarity_str in matches:
            if a_name:
                obj_b.vertex_groups[b_name].name = a_name
                renamed_count += 1
        
        return {
            'renamed_count': renamed_count,
            'matches': matches,
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
        
        for b_name, a_name, similarity in result['matches']:

            if a_name:
                matched += 1
                print(f"{b_name:<30} → {a_name:<30} {similarity:<20}")
            else:
                unmatched += 1
                print(f"{b_name:<30} → {'保留原名称':<30} {'(未匹配)':<20}")

        
        print(separator)
        print("总结:")
        print(f"  源A物体非空顶点组数量: {result['total_a']}")
        print(f"  目标B物体非空顶点组数量: {result['total_b']}")
        print(f"  匹配数量: {matched}")
        print(f"  未匹配数量: {unmatched}")
        print(f"  总重命名数量: {result['renamed_count']}")
        print(separator)


# ----------------------------------------------------------------
# 4. 名称排序操作 (Sort Match Operator) - 💥 优化并增加反馈
# ----------------------------------------------------------------
class O_VertexGroupsSortMatch(bpy.types.Operator):
    bl_idname = "xbone.vertex_groups_sort_match"
    bl_label = "名称排序 (高效)"
    bl_description = ("严格按照选择物体的顶点组顺序重新排列活动物体的顶点组\n"
                     "使用高效算法：保存权重 -> 清空 -> 按顺序重建/恢复权重")

    def execute(self, context):
        start_time = time.time()  # 记录开始时间
        
        try:
            selected_objs = context.selected_objects
            active_obj = context.active_object
            
            # 验证选择
            if len(selected_objs) != 2:
                raise ValueError("请选择2个网格物体")
                
            if active_obj not in selected_objs:
                raise ValueError("活动物体必须是选中的物体之一")
                
            source_obj = next(obj for obj in selected_objs if obj != active_obj)
            target_obj = active_obj

            if source_obj.type != 'MESH' or target_obj.type != 'MESH':
                raise ValueError("两个物体都必须是网格类型")
            
            # 确保处于对象模式以操作顶点组
            if context.mode != 'OBJECT':
                 raise ValueError("请切换到对象模式 (Object Mode)")
            
            # 执行排序
            result = self._sort_vertex_groups_optimized(target_obj, source_obj)
            
            # 打印详细结果到控制台
            self._print_detailed_results(source_obj, target_obj, result)
            
            # 计算总耗时
            elapsed_time = time.time() - start_time
            time_msg = f"总耗时: {elapsed_time:.4f}秒"
            
            self.report({'INFO'}, 
                       f"排序完成: 匹配 {result['matched']}个, 新建 {result['added']}个 ({time_msg})")
            
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
    bpy.utils.register_class(O_VertexGroupsCount)
    bpy.utils.register_class(O_VertexGroupsDelNoneActive)
    bpy.utils.register_class(O_VertexGroupsMatchRename)
    bpy.utils.register_class(O_VertexGroupsSortMatch)

    bpy.types.Scene.similarity_threshold = bpy.props.FloatProperty(
        name="顶点组相似度阈值",
        description="匹配顶点组时的最小相似度(0-1)",
        default=0.94,
        min=0.9,
        max=1.0,
        step=0.01,
        precision=3
    )

def unregister():
    bpy.utils.unregister_class(DATA_PT_vertex_group_tools)
    bpy.utils.unregister_class(O_VertexGroupsCount)
    bpy.utils.unregister_class(O_VertexGroupsDelNoneActive)
    bpy.utils.unregister_class(O_VertexGroupsMatchRename)
    bpy.utils.unregister_class(O_VertexGroupsSortMatch)

    del bpy.types.Scene.similarity_threshold
