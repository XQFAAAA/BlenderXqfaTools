# type: ignore
import bpy
import numpy as np
import time
from typing import Dict, Tuple, Set, List, Optional

class DATA_PT_shape_key_tools(bpy.types.Panel):
    bl_label = "形态键"
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
        col.operator(O_ShapeKeysMatchRename.bl_idname, text=O_ShapeKeysMatchRename.bl_label, icon="SORTBYEXT")
        col.operator(O_ShapeKeysSortMatch.bl_idname, text=O_ShapeKeysSortMatch.bl_label, icon="SORTSIZE")
        col.operator(O_ShapeKeysRenameByOrder.bl_idname, text=O_ShapeKeysRenameByOrder.bl_label, icon="SORTALPHA")
        col.separator()
        col.operator(O_ShapeKeysSelectAffectedVertices.bl_idname, text=O_ShapeKeysSelectAffectedVertices.bl_label, icon="VERTEXSEL")
        col.operator(O_ShapeKeysClean.bl_idname, text=O_ShapeKeysClean.bl_label, icon="BRUSH_DATA")
        col.operator(O_ShapeKeysTransfer.bl_idname, text=O_ShapeKeysTransfer.bl_label, icon="SHAPEKEY_DATA")

class O_ShapeKeysMatchRename(bpy.types.Operator):
    bl_idname = "xqfa.shape_keys_match_rename"
    bl_label = "匹配重命名"
    bl_description = ("基于顶点平均位置匹配重命名活动物体的形态键（需选择2个网格物体）\n"
                     "用于按参考模型的形态键名称重命名当前模型的形态键")

    similarity_threshold: bpy.props.FloatProperty(
        name="相似度",
        description="匹配形态键时的最小相似度(0-1)",
        default=0.94,
        min=0.5,
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
        start_time = time.time()
        
        try:
            # 验证输入并获取目标物体
            obj_a, obj_b = self._validate_input(context)
            
            # 执行匹配重命名并获取详细结果
            result = self._rename_matching_shape_keys(obj_a, obj_b)
            
            # 打印详细结果到控制台
            self._print_detailed_results(obj_a, obj_b, result)
            
            elapsed_time = time.time() - start_time
            time_msg = f"总耗时: {elapsed_time:.2f}秒"
            
            if result['renamed_count'] > 0:
                self.report({'INFO'}, f"成功匹配重命名 {result['renamed_count']} 个形态键 ({time_msg})")
            else:
                self.report({'WARNING'}, f"没有找到匹配的形态键 ({time_msg})")
                
            return {'FINISHED'}
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            self.report({'ERROR'}, f"{str(e)} (耗时: {elapsed_time:.2f}秒)")
            return {'CANCELLED'}
    
    def _validate_input(self, context: bpy.types.Context) -> Tuple[bpy.types.Object, bpy.types.Object]:
        """验证输入并返回两个有形态键的网格物体"""
        selected_objs = context.selected_objects
        active_obj = context.active_object
        
        if len(selected_objs) != 2:
            raise ValueError("请选择2个网格物体")
            
        if active_obj not in selected_objs:
            raise ValueError("活动物体必须是选中的物体之一")
            
        obj_b = active_obj
        obj_a = next(obj for obj in selected_objs if obj != active_obj)
        
        if obj_a.type != 'MESH' or obj_b.type != 'MESH':
            raise ValueError("两个物体都必须是网格类型")
            
        if not obj_a.data.shape_keys or not obj_b.data.shape_keys:
            raise ValueError("两个物体都必须有形态键")
            
        return obj_a, obj_b
    
    def _get_shape_key_centers(self, obj: bpy.types.Object) -> Dict[str, np.ndarray]:
        """获取每个形态键的顶点平均位置"""
        centers = {}
        mesh = obj.data
        shape_keys = mesh.shape_keys.key_blocks
        
        # 获取基础网格顶点坐标
        base_verts = np.zeros(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get('co', base_verts)
        base_verts = base_verts.reshape(-1, 3)
        
        for sk in shape_keys:
            if sk == sk.relative_key:  # 跳过基础形态键
                continue
                
            # 获取形态键的相对顶点坐标
            sk_verts = np.zeros(len(mesh.vertices) * 3)
            sk.data.foreach_get('co', sk_verts)
            sk_verts = sk_verts.reshape(-1, 3)
            
            # 计算绝对顶点位置
            abs_verts = base_verts + sk_verts
            
            # 转换为全局坐标
            matrix = np.array(obj.matrix_world)
            global_verts = np.dot(abs_verts, matrix[:3, :3].T) + matrix[:3, 3]
            
            # 计算平均位置
            centers[sk.name] = np.mean(global_verts, axis=0)
        
        return centers
    
    def _calculate_similarity(self, pos_a: np.ndarray, pos_b: np.ndarray) -> float:
        """计算两个位置之间的相似度（基于距离）"""
        distance = np.linalg.norm(pos_a - pos_b)
        return 1.0 / (1.0 + distance)
    
    def _rename_matching_shape_keys(self, 
                                  obj_a: bpy.types.Object, 
                                  obj_b: bpy.types.Object) -> Dict[str, any]:
        """匹配并重命名形态键"""
        centers_a = self._get_shape_key_centers(obj_a)
        centers_b = self._get_shape_key_centers(obj_b)
        
        if not centers_a:
            raise Exception("A物体没有可用的形态键（只有基础形态键）")
        if not centers_b:
            raise Exception("B物体没有可用的形态键（只有基础形态键）")
        
        renamed_count = 0
        matched_a_keys: Set[str] = set()
        matches: List[Tuple[str, Optional[str], str]] = []
        
        shape_keys_b = obj_b.data.shape_keys.key_blocks
        
        for b_name, b_center in centers_b.items():
            best_match_name = None
            best_similarity = 0.0
            
            for a_name, a_center in centers_a.items():
                if a_name in matched_a_keys:
                    continue
                    
                similarity = self._calculate_similarity(a_center, b_center)
                if similarity > best_similarity and similarity >= self.similarity_threshold:
                    best_similarity = similarity
                    best_match_name = a_name
            
            if best_match_name:
                shape_keys_b[b_name].name = best_match_name
                matched_a_keys.add(best_match_name)
                renamed_count += 1
                matches.append((b_name, best_match_name, f"{best_similarity:.3f}"))
            else:
                matches.append((b_name, None, "no match"))
        
        return {
            'renamed_count': renamed_count,
            'matches': matches,
            'total_a': len(centers_a),
            'total_b': len(centers_b)
        }
    
    def _print_detailed_results(self, 
                              obj_a: bpy.types.Object, 
                              obj_b: bpy.types.Object, 
                              result: Dict[str, any]) -> None:
        """打印详细结果到控制台"""
        header = f"形态键匹配与重命名详细结果 (A物体: {obj_a.name}, B物体: {obj_b.name})"
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
                print(f"{b_name:<30} → {'保留原名称':<30} {'(未匹配)':<20}")
                unmatched += 1
        
        print(separator)
        print("总结:")
        print(f"  A物体形态键数量: {result['total_a']}")
        print(f"  B物体形态键数量: {result['total_b']}")
        print(f"  匹配数量: {matched}")
        print(f"  未匹配数量: {unmatched}")
        print(f"  总重命名数量: {result['renamed_count']}")
        print(separator)

class O_ShapeKeysSortMatch(bpy.types.Operator):
    bl_idname = "xqfa.shape_keys_sort_match"
    bl_label = "按名称排序"
    bl_description = ("严格按照选择物体的形态键名称顺序重新排列活动物体的形态键\n"
                    "操作逻辑:\n"
                    "1. 按选择物体的形态键顺序依次处理\n"
                    "2. 缺少的形态键会新建空键\n"
                    "3. 已有的形态键会移动到对应位置\n"
                    "4. 多余的形态键会保留在最后")

    def execute(self, context):
        try:
            selected_objs = context.selected_objects
            active_obj = context.active_object
            
            # 验证选择
            if len(selected_objs) != 2:
                self.report({'ERROR'}, "请选择2个网格物体")
                return {'CANCELLED'}
                
            if active_obj not in selected_objs:
                self.report({'ERROR'}, "活动物体必须是选中的物体之一")
                return {'CANCELLED'}
                
            source_obj = next(obj for obj in selected_objs if obj != active_obj)
            target_obj = active_obj

            if source_obj.type != 'MESH' or target_obj.type != 'MESH':
                self.report({'ERROR'}, "两个物体都必须是网格类型")
                return {'CANCELLED'}
                
            if not source_obj.data.shape_keys:
                self.report({'ERROR'}, "源物体必须有形态键")
                return {'CANCELLED'}
                
            # 执行精确排序
            result = self._reorder_shape_keys_exact(source_obj, target_obj)
            
            self.report({'INFO'}, 
                       f"排序完成: 匹配 {result['matched']}个, "
                       f"添加 {result['added']}个, "
                       f"保留 {result['kept']}个")
            
            # 打印详细结果到控制台
            print(f"\n形态键排序结果 [{target_obj.name} → {source_obj.name}]:")
            for i, sk in enumerate(target_obj.data.shape_keys.key_blocks):
                prefix = "  ✓ " if sk.name in [x.name for x in source_obj.data.shape_keys.key_blocks] else "  + " if sk.name not in result['original_keys'] else "  ✕ "
                print(f"{i+1:2d}.{prefix}{sk.name}")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
    
    def _reorder_shape_keys_exact(self, source_obj, target_obj):
        source_sks = source_obj.data.shape_keys.key_blocks
        target_sks = target_obj.data.shape_keys.key_blocks if target_obj.data.shape_keys else None
        
        # 记录目标物体原有的形态键名称
        original_keys = set()
        if target_sks:
            original_keys = {sk.name for sk in target_sks}
        
        # 确保目标物体有形态键
        if not target_sks:
            target_obj.shape_key_add(name="Basis", from_mix=False)
            target_sks = target_obj.data.shape_keys.key_blocks
        
        # 我们需要知道每个形态键应该移动到的位置
        desired_order = []
        added_count = 0
        matched_count = 0
        
        # 首先处理基础形态键
        basis_sk = target_sks.get("Basis")
        if not basis_sk:
            basis_sk = target_sks[0] if len(target_sks) > 0 else target_obj.shape_key_add(name="Basis", from_mix=False)
        
        # 确保基础形态键在第一位
        if basis_sk != target_sks[0]:
            target_obj.active_shape_key_index = basis_sk.index
            for _ in range(basis_sk.index):
                bpy.ops.object.shape_key_move(type='UP')
        
        # 遍历源物体的形态键顺序
        for src_sk in source_sks:
            if src_sk.name == "Basis":
                continue  # 基础形态键已经在第一位
            
            # 检查目标物体是否有该形态键
            if src_sk.name in target_sks:
                # 已有形态键，记录需要移动到的位置
                desired_order.append(src_sk.name)
                matched_count += 1
            else:
                # 没有该形态键，添加一个新的空形态键
                new_sk = target_obj.shape_key_add(name=src_sk.name, from_mix=False)
                desired_order.append(new_sk.name)
                added_count += 1
        
        # 添加目标物体独有的形态键到末尾
        kept_count = 0
        for tgt_sk in target_sks:
            if tgt_sk.name not in desired_order and tgt_sk.name != "Basis":
                desired_order.append(tgt_sk.name)
                kept_count += 1
        
        # 现在按照desired_order重新排列形态键
        # 由于Blender没有直接重排API，我们需要通过移动来实现
        for desired_index, sk_name in enumerate(desired_order):
            if desired_index == 0:
                continue  # 基础形态键已经在第一位
            
            current_index = target_sks.find(sk_name)
            if current_index == -1:
                continue  # 不应该发生
            
            # 计算需要移动的次数
            move_count = current_index - desired_index
            if move_count <= 0:
                continue  # 已经在正确位置或更靠前
            
            # 移动形态键到正确位置
            target_obj.active_shape_key_index = current_index
            for _ in range(move_count):
                bpy.ops.object.shape_key_move(type='UP')
        
        return {
            'matched': matched_count,
            'added': added_count,
            'kept': kept_count,
            'original_keys': original_keys
        }
    
class O_ShapeKeysRenameByOrder(bpy.types.Operator):
    bl_idname = "xqfa.shape_keys_rename_by_order"
    bl_label = "顺序重命名"
    bl_description = ("按照选择物体A的形态键顺序重命名活动物体B的形态键名称\n"
                     "操作逻辑:\n"
                     "1. 跳过基础形态键('Basis')\n"
                     "2. 按顺序将B物体的形态键重命名为A物体的形态键名称\n"
                     "3. 如果B物体的形态键比A物体多，多余的保留原名\n"
                     "示例:\n"
                     "A物体: ['Basis','TT','XX','YY']\n"
                     "B物体: ['Basis','1','2','3','4']\n"
                     "结果: ['Basis','TT','XX','YY','4']")

    def execute(self, context):
        try:
            selected_objs = context.selected_objects
            active_obj = context.active_object
            
            # 验证选择
            if len(selected_objs) != 2:
                self.report({'ERROR'}, "请选择2个网格物体")
                return {'CANCELLED'}
                
            if active_obj not in selected_objs:
                self.report({'ERROR'}, "活动物体必须是选中的物体之一")
                return {'CANCELLED'}
                
            source_obj = next(obj for obj in selected_objs if obj != active_obj)
            target_obj = active_obj

            if source_obj.type != 'MESH' or target_obj.type != 'MESH':
                self.report({'ERROR'}, "两个物体都必须是网格类型")
                return {'CANCELLED'}
                
            if not source_obj.data.shape_keys:
                self.report({'ERROR'}, "源物体必须有形态键")
                return {'CANCELLED'}
                
            if not target_obj.data.shape_keys:
                self.report({'ERROR'}, "目标物体必须有形态键")
                return {'CANCELLED'}
                
            # 执行顺序重命名
            result = self._rename_shape_keys_by_order(source_obj, target_obj)
            
            self.report({'INFO'}, 
                       f"重命名完成: 已重命名 {result['renamed']}个, "
                       f"保留 {result['kept']}个")
            
            # 打印详细结果到控制台
            print(f"\n形态键顺序重命名结果 [{target_obj.name} → {source_obj.name}]:")
            source_names = [sk.name for sk in source_obj.data.shape_keys.key_blocks]
            for i, sk in enumerate(target_obj.data.shape_keys.key_blocks):
                if i == 0:
                    print(f"{i+1:2d}.   {sk.name} (Basis)")
                elif i-1 < len(source_names)-1:
                    renamed = sk.name in source_names
                    prefix = "  ✓ " if renamed else "  ✕ "
                    print(f"{i+1:2d}.{prefix}{sk.name}")
                else:
                    print(f"{i+1:2d}.  ✕ {sk.name} (保留)")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
    
    def _rename_shape_keys_by_order(self, source_obj, target_obj):
        source_sks = source_obj.data.shape_keys.key_blocks
        target_sks = target_obj.data.shape_keys.key_blocks
        
        renamed_count = 0
        kept_count = 0
        
        # 跳过基础形态键
        source_index = 1  # 从第二个形态键开始
        target_index = 1
        
        # 遍历目标物体的形态键(跳过基础形态键)
        while target_index < len(target_sks) and source_index < len(source_sks):
            target_sk = target_sks[target_index]
            source_name = source_sks[source_index].name
            
            # 重命名目标形态键
            target_sk.name = source_name
            renamed_count += 1
            
            source_index += 1
            target_index += 1
        
        # 计算保留的形态键数量
        kept_count = max(0, len(target_sks) - source_index)
        
        return {
            'renamed': renamed_count,
            'kept': kept_count
        }

class O_ShapeKeysSelectAffectedVertices(bpy.types.Operator):
    bl_idname = "xqfa.shape_keys_select_affected_vertices"
    bl_label = "选中影响顶点"
    bl_description = ("选中当前形态键影响的顶点\n"
                     "选中与基础形态键位置有差异的顶点")

    select_threshold: bpy.props.FloatProperty(
        name="阈值",
        description="顶点位置差异的最小阈值（米）",
        default=0.0001,
        min=0.0,
        step=0.0001,
        precision=5
    )

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=200)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "select_threshold")

    def execute(self, context):
        try:
            obj = context.active_object
            
            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "请选择一个网格物体")
                return {'CANCELLED'}
            
            if not obj.data.shape_keys:
                self.report({'ERROR'}, "物体没有形态键")
                return {'CANCELLED'}
            
            if not obj.data.shape_keys.use_relative:
                self.report({'ERROR'}, "仅支持相对形态键")
                return {'CANCELLED'}
            
            current_sk = obj.active_shape_key
            if not current_sk:
                self.report({'ERROR'}, "没有激活的形态键")
                return {'CANCELLED'}
            
            if current_sk == current_sk.relative_key:
                self.report({'ERROR'}, "当前是基础形态键，请选择其他形态键")
                return {'CANCELLED'}
            
            result = self._select_affected_vertices(obj, current_sk, self.select_threshold)
            
            self.report({'INFO'}, f"已选中 {result['count']} 个顶点")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
    
    def _select_affected_vertices(self, obj, shape_key, threshold):
        """选中与基础形态键有差异的顶点"""
        mesh = obj.data
        shape_keys = mesh.shape_keys
        base_key = shape_key.relative_key
        
        # 获取顶点总数
        total_verts = len(mesh.vertices)
        
        # 获取基础形态键顶点坐标
        base_coords = np.zeros(total_verts * 3)
        base_key.data.foreach_get('co', base_coords)
        base_coords = base_coords.reshape(-1, 3)
        
        # 获取当前形态键顶点坐标
        sk_coords = np.zeros(total_verts * 3)
        shape_key.data.foreach_get('co', sk_coords)
        sk_coords = sk_coords.reshape(-1, 3)
        
        # 计算差异距离
        diffs = np.linalg.norm(sk_coords - base_coords, axis=1)
        
        # 切换到编辑模式（如果还没在）
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # 首先取消所有选择
        bpy.ops.mesh.select_all(action='DESELECT')
        
        # 切换回对象模式来设置顶点选择
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # 选中有差异的顶点
        affected_count = 0
        for i, diff in enumerate(diffs):
            if diff > threshold:
                mesh.vertices[i].select = True
                affected_count += 1
        
        # 回到编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        
        return {
            'count': affected_count,
            'total': total_verts
        }


class O_ShapeKeysClean(bpy.types.Operator):
    bl_idname = "xqfa.shape_keys_clean"
    bl_label = "清理形态键"
    bl_description = ("删除所有不影响任何顶点的形态键（与基础形态键无差异的形态键）\n"
                     "仅保留有实际顶点偏移的形态键")

    clean_threshold: bpy.props.FloatProperty(
        name="阈值",
        description="顶点位置差异的最小阈值（米），低于此值视为无影响",
        default=0.0001,
        min=0.0,
        step=0.0001,
        precision=5
    )

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=200)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "clean_threshold")

    def execute(self, context):
        try:
            obj = context.active_object

            if not obj or obj.type != 'MESH':
                self.report({'ERROR'}, "请选择一个网格物体")
                return {'CANCELLED'}

            if not obj.data.shape_keys:
                self.report({'ERROR'}, "物体没有形态键")
                return {'CANCELLED'}

            if not obj.data.shape_keys.use_relative:
                self.report({'ERROR'}, "仅支持相对形态键")
                return {'CANCELLED'}

            result = self._clean_empty_shape_keys(obj, self.clean_threshold)

            if result['removed'] > 0:
                self.report({'INFO'},
                           f"已删除 {result['removed']} 个无效形态键，"
                           f"保留 {result['kept']} 个有效形态键")
            else:
                self.report({'INFO'}, "所有形态键均有效，无需清理")

            # 打印详细结果
            if result['removed_names']:
                print(f"\n形态键清理结果 [{obj.name}]:")
                for name in result['removed_names']:
                    print(f"  ✕ {name} (已删除)")
                for name in result['kept_names']:
                    print(f"  ✓ {name} (保留)")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

    def _clean_empty_shape_keys(self, obj, threshold):
        """删除与基础形态键无差异的形态键"""
        mesh = obj.data
        shape_keys = mesh.shape_keys
        key_blocks = shape_keys.key_blocks
        base_key = key_blocks[0]  # Basis

        total_verts = len(mesh.vertices)

        # 获取基础形态键顶点坐标
        base_coords = np.zeros(total_verts * 3)
        base_key.data.foreach_get('co', base_coords)
        base_coords = base_coords.reshape(-1, 3)

        # 收集需要删除的形态键名称（从后往前收集，避免删除时索引变化）
        removed_names = []
        kept_names = []

        for sk in key_blocks:
            if sk == sk.relative_key:
                kept_names.append(sk.name)
                continue

            sk_coords = np.zeros(total_verts * 3)
            sk.data.foreach_get('co', sk_coords)
            sk_coords = sk_coords.reshape(-1, 3)

            diffs = np.linalg.norm(sk_coords - base_coords, axis=1)
            max_diff = np.max(diffs)

            if max_diff <= threshold:
                removed_names.append(sk.name)
            else:
                kept_names.append(sk.name)

        # 从后往前删除，避免索引变化问题
        for name in reversed(removed_names):
            obj.shape_key_remove(key_blocks[name])

        return {
            'removed': len(removed_names),
            'kept': len(kept_names),
            'removed_names': removed_names,
            'kept_names': kept_names,
        }


class O_ShapeKeysTransfer(bpy.types.Operator):
    bl_idname = "xqfa.shape_keys_transfer"
    bl_label = "传递形态键"
    bl_description = "将选择物体A的所有形态键传递给活动物体B（顶点ID需一致）"

    def execute(self, context):
        selected_objs = context.selected_objects
        active_obj = context.active_object

        if len(selected_objs) != 2:
            self.report({'ERROR'}, "请选择2个网格物体")
            return {'CANCELLED'}

        if active_obj not in selected_objs:
            self.report({'ERROR'}, "活动物体必须是选中的物体之一")
            return {'CANCELLED'}

        source_obj = next(obj for obj in selected_objs if obj != active_obj)
        target_obj = active_obj

        if source_obj.type != 'MESH' or target_obj.type != 'MESH':
            self.report({'ERROR'}, "两个物体都必须是网格类型")
            return {'CANCELLED'}

        if not source_obj.data.shape_keys:
            self.report({'ERROR'}, "源物体没有形态键")
            return {'CANCELLED'}

        src_verts_count = len(source_obj.data.vertices)
        tgt_verts_count = len(target_obj.data.vertices)
        if src_verts_count != tgt_verts_count:
            self.report({'ERROR'}, f"顶点数不一致: 源{src_verts_count} ≠ 目标{tgt_verts_count}")
            return {'CANCELLED'}

        # 确保目标物体有形态键基础
        if not target_obj.data.shape_keys:
            target_obj.shape_key_add(name="Basis", from_mix=False)

        source_sks = source_obj.data.shape_keys.key_blocks
        target_sks = target_obj.data.shape_keys.key_blocks

        transferred = 0
        for src_sk in source_sks:
            if src_sk.name == "Basis":
                continue

            # 检查目标是否已有同名形态键，没有则创建
            tgt_sk = target_sks.get(src_sk.name)
            if not tgt_sk:
                tgt_sk = target_obj.shape_key_add(name=src_sk.name, from_mix=False)

            # 获取源形态键顶点数据
            src_data = np.zeros(src_verts_count * 3, dtype=np.float32)
            src_sk.data.foreach_get('co', src_data)

            # 写入目标形态键
            tgt_sk.data.foreach_set('co', src_data)

            transferred += 1

        self.report({'INFO'}, f"已传递 {transferred} 个形态键: {source_obj.name} → {target_obj.name}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(DATA_PT_shape_key_tools)
    bpy.utils.register_class(O_ShapeKeysMatchRename)
    bpy.utils.register_class(O_ShapeKeysSortMatch)
    bpy.utils.register_class(O_ShapeKeysRenameByOrder)
    bpy.utils.register_class(O_ShapeKeysSelectAffectedVertices)
    bpy.utils.register_class(O_ShapeKeysClean)
    bpy.utils.register_class(O_ShapeKeysTransfer)

def unregister():
    bpy.utils.unregister_class(DATA_PT_shape_key_tools)
    bpy.utils.unregister_class(O_ShapeKeysMatchRename)
    bpy.utils.unregister_class(O_ShapeKeysSortMatch)
    bpy.utils.unregister_class(O_ShapeKeysRenameByOrder)
    bpy.utils.unregister_class(O_ShapeKeysSelectAffectedVertices)
    bpy.utils.unregister_class(O_ShapeKeysClean)
    bpy.utils.unregister_class(O_ShapeKeysTransfer)
