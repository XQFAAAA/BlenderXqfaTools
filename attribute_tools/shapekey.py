# type: ignore
import bpy
import numpy as np
import time
from typing import Dict, Tuple, Set, List, Optional
from bpy.props import IntProperty, FloatProperty, PointerProperty

class XQFA_Utils:
    @staticmethod
    def is_mesh(scene, obj):
        return obj.type == "MESH"
    
    @staticmethod
    def is_armature(scene, obj):
        return obj.type == "ARMATURE"

class XqfaShapeKeyPairItem(bpy.types.PropertyGroup):
    left_name: bpy.props.StringProperty(name="左")
    right_name: bpy.props.StringProperty(name="右")
    similarity: bpy.props.StringProperty(name="相似度", default="")


class XqfaShapeKeyMappingItem(bpy.types.PropertyGroup):
    expanded: bpy.props.BoolProperty(name="展开", default=False)
    label: bpy.props.StringProperty(name="标题")
    pairs: bpy.props.CollectionProperty(type=XqfaShapeKeyPairItem)
    active_pair_index: bpy.props.IntProperty(default=0)


class SKPairList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=item.left_name)
            row.label(text="↔")
            row.label(text=item.right_name)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="")


class DATA_PT_shape_key_tools(bpy.types.Panel):
    bl_label = "形态键"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
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

        row = col.row(align=True)
        row.prop(context.scene, "sk_source_mesh", text = "", icon="MESH_DATA")
        if context.scene.sk_source_mesh:
            armature_mod = None
            armature_modifiers = [mod for mod in context.scene.sk_source_mesh.modifiers if mod.type == 'ARMATURE']
            
            if armature_modifiers:
                if len(armature_modifiers) == 1:
                    armature_mod = armature_modifiers[0]
                    row.label(text=f"骨架: {armature_mod.object.name if armature_mod.object else '无'}", icon='ARMATURE_DATA')
                else:
                    row.label(text="错误: 物体有多个骨架修改器", icon='ERROR')
            else:
                row.label(text="错误: 物体没有骨架修改器", icon='ERROR')
        row.operator(XQFA_OT_ApplyAsShapekey.bl_idname, icon="SHAPEKEY_DATA")

        self._draw_mappings(context)

    def _draw_mappings(self, context):
        scene = context.scene
        mappings = getattr(scene, 'xqfa_shape_key_mappings', None)
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
            icon = "TRIA_DOWN" if item.expanded else "TRIA_RIGHT"
            row.prop(item, "expanded", icon=icon, icon_only=True, emboss=False)
            if not item.label:
                item.label = f"映射 {idx + 1}"
            row.prop(item, "label", text="")
            row.label(text=f"({len(item.pairs)}项)")
            row.separator(factor=1.0)
            op_lr = row.operator(O_ShapeKeyMappingApply.bl_idname, text="", icon="FORWARD")
            op_lr.index = idx
            op_lr.direction = "LEFT_TO_RIGHT"
            op_rl = row.operator(O_ShapeKeyMappingApply.bl_idname, text="", icon="BACK")
            op_rl.index = idx
            op_rl.direction = "RIGHT_TO_LEFT"
            op_l_order = row.operator(O_ShapeKeyMappingReorder.bl_idname, text="", icon="EVENT_L")
            op_l_order.index = idx
            op_l_order.direction = "LEFT"
            op_r_order = row.operator(O_ShapeKeyMappingReorder.bl_idname, text="", icon="EVENT_R")
            op_r_order.index = idx
            op_r_order.direction = "RIGHT"
            row.operator(O_ShapeKeyMappingRemove.bl_idname, text="", icon="X").index = idx
            if item.expanded:
                box.template_list(
                    "SKPairList",
                    f"sk_pairs_{idx}",
                    item,
                    "pairs",
                    item,
                    "active_pair_index",
                    type='DEFAULT',
                )


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

    mapping_name: bpy.props.StringProperty(
        name="映射名称",
        description="存储映射记录时使用的标签名称",
        default=""
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
            obj_a, obj_b = self._validate_input(context)

            result = self._rename_matching_shape_keys(obj_a, obj_b)

            self._print_detailed_results(obj_a, obj_b, result)

            self._store_mapping(context, obj_a, obj_b, result)

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

    def _store_mapping(self, context, obj_a, obj_b, result):
        scene = context.scene
        if not hasattr(scene, 'xqfa_shape_key_mappings'):
            return
        mappings = scene.xqfa_shape_key_mappings
        item = mappings.add()
        item.label = self.mapping_name if self.mapping_name else f"映射 {len(mappings)}"
        item.expanded = False
        pair_items = result.get('pair_items', [])
        for left_name, right_name, similarity in pair_items:
            p = item.pairs.add()
            p.left_name = left_name
            p.right_name = right_name
            p.similarity = similarity
    
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

        match_lookup: Dict[str, Tuple[Optional[str], str]] = {}
        matched_a_keys: Set[str] = set()

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
                matched_a_keys.add(best_match_name)
                match_lookup[b_name] = (best_match_name, f"{best_similarity:.3f}")
            else:
                match_lookup[b_name] = (None, "no match")

        shape_keys_b = obj_b.data.shape_keys.key_blocks
        original_sk_names = [sk.name for sk in shape_keys_b]

        renamed_count = 0
        pair_items: List[Tuple[str, str, str]] = []

        for orig_name in original_sk_names:
            sk = shape_keys_b[orig_name]
            if sk == sk.relative_key:
                continue

            match_info = match_lookup.get(orig_name, (None, "-"))
            a_name, similarity_str = match_info
            if a_name:
                shape_keys_b[orig_name].name = a_name
                pair_items.append((orig_name, a_name, similarity_str))
                renamed_count += 1
            else:
                pair_items.append((orig_name, orig_name, similarity_str))

        return {
            'renamed_count': renamed_count,
            'pair_items': pair_items,
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

        for left_name, right_name, similarity_str in result['pair_items']:
            if left_name != right_name:
                matched += 1
                print(f"{left_name:<30} → {right_name:<30} {similarity_str:<20}")
            else:
                unmatched += 1
                print(f"{left_name:<30} → {'保留原名称':<30} {similarity_str:<20}")

        print(separator)
        print("总结:")
        print(f"  A物体形态键数量: {result['total_a']}")
        print(f"  B物体形态键数量: {result['total_b']}")
        print(f"  匹配数量: {matched}")
        print(f"  未匹配数量: {unmatched}")
        print(f"  总重命名数量: {result['renamed_count']}")
        print(separator)

class O_ShapeKeyMappingRemove(bpy.types.Operator):
    bl_idname = "xqfa.shape_key_mapping_remove"
    bl_label = "关闭映射"
    bl_description = "从列表中移除此映射记录"

    index: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        mappings = getattr(scene, 'xqfa_shape_key_mappings', None)
        if mappings is None:
            return {'CANCELLED'}
        if self.index < 0 or self.index >= len(mappings):
            return {'CANCELLED'}
        mappings.remove(self.index)
        return {'FINISHED'}


class O_ShapeKeyMappingApply(bpy.types.Operator):
    bl_idname = "xqfa.shape_key_mapping_apply"
    bl_label = "应用映射"
    bl_description = "按映射关系重命名两个物体的形态键"

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
        mappings = getattr(scene, 'xqfa_shape_key_mappings', None)
        if mappings is None or self.index < 0 or self.index >= len(mappings):
            return {'CANCELLED'}
        item = mappings[self.index]

        selected_objs = [o for o in context.selected_objects if o.type == 'MESH' and o.data.shape_keys]
        if not selected_objs:
            self.report({'ERROR'}, "请先选择有形态键的网格物体")
            return {'CANCELLED'}

        if self.direction == "LEFT_TO_RIGHT":
            lookup = [(p.left_name, p.right_name) for p in item.pairs]
        else:
            lookup = [(p.right_name, p.left_name) for p in item.pairs]

        total_renamed = 0
        total_skipped = 0
        affected_objs = 0

        for obj in selected_objs:
            sk_blocks = obj.data.shape_keys.key_blocks
            obj_renamed = 0
            for old_name, new_name in lookup:
                idx = sk_blocks.find(old_name)
                if idx == -1:
                    total_skipped += 1
                    continue
                try:
                    sk_blocks[idx].name = new_name
                    obj_renamed += 1
                except Exception:
                    total_skipped += 1
            if obj_renamed > 0:
                total_renamed += obj_renamed
                affected_objs += 1

        self.report({'INFO'}, f"影响 {affected_objs}/{len(selected_objs)} 个物体：已重命名 {total_renamed} 项，跳过 {total_skipped} 项")
        return {'FINISHED'}


class O_ShapeKeyMappingReorder(bpy.types.Operator):
    bl_idname = "xqfa.shape_key_mapping_reorder"
    bl_label = "按映射顺序重排形态键"
    bl_description = "按映射记录中左侧（或右侧）名称的顺序，重排选中物体的形态键（保留数据，缺失项新建空键，多余项放到末尾）"

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
        mappings = getattr(scene, 'xqfa_shape_key_mappings', None)
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
            result = self._reorder_shape_keys(obj, desired_names)
            total_matched += result['matched']
            total_added += result['added']
            total_extra += result['extra']

        self.report(
            {'INFO'},
            f"已在 {len(target_objs)} 个物体上调整顺序 (共 {total_matched} 匹配, {total_added} 新建空键, {total_extra} 保留到末尾)"
        )
        return {'FINISHED'}

    def _reorder_shape_keys(self, target_obj, desired_order):
        if not target_obj.data.shape_keys or len(target_obj.data.shape_keys.key_blocks) == 0:
            target_obj.shape_key_add(name="Basis", from_mix=False)

        key_blocks = target_obj.data.shape_keys.key_blocks
        num_verts = len(target_obj.data.vertices)

        shape_data = {}
        for sk in key_blocks:
            coords = np.empty(num_verts * 3, dtype=np.float32)
            sk.data.foreach_get('co', coords)
            shape_data[sk.name] = coords

        original_names = [sk.name for sk in key_blocks]
        basis_name = key_blocks[0].name

        for i in range(len(key_blocks) - 1, 0, -1):
            target_obj.shape_key_remove(key_blocks[i])

        matched = 0
        added = 0
        extra = 0
        used_names = {basis_name}

        for name in desired_order:
            if name in used_names:
                continue

            new_sk = target_obj.shape_key_add(name=name, from_mix=False)
            if name in shape_data:
                coords = shape_data.pop(name)
                new_sk.data.foreach_set('co', coords)
                new_sk.data.update()
                matched += 1
            else:
                added += 1
            used_names.add(name)

        for extra_name in list(shape_data.keys()):
            if extra_name == basis_name:
                continue
            if extra_name in used_names:
                continue
            new_sk = target_obj.shape_key_add(name=extra_name, from_mix=False)
            coords = shape_data.pop(extra_name)
            new_sk.data.foreach_set('co', coords)
            new_sk.data.update()
            extra += 1
            used_names.add(extra_name)

        return {
            'matched': matched,
            'added': added,
            'extra': extra,
            'original_total': len(original_names),
            'order_total': len(desired_order),
        }


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
            selected_objs = [obj for obj in context.selected_objects if obj.type == 'MESH']

            if not selected_objs:
                self.report({'ERROR'}, "请选择至少一个网格物体")
                return {'CANCELLED'}

            total_removed = 0
            total_kept = 0
            processed = 0

            for obj in selected_objs:
                if not obj.data.shape_keys:
                    print(f"跳过 {obj.name}: 没有形态键")
                    continue

                if not obj.data.shape_keys.use_relative:
                    print(f"跳过 {obj.name}: 非相对形态键")
                    continue

                result = self._clean_empty_shape_keys(obj, self.clean_threshold)
                total_removed += result['removed']
                total_kept += result['kept']
                processed += 1

                if result['removed_names']:
                    print(f"\n形态键清理结果 [{obj.name}]:")
                    for name in result['removed_names']:
                        print(f"  ✕ {name} (已删除)")
                    for name in result['kept_names']:
                        print(f"  ✓ {name} (保留)")

            if processed == 0:
                self.report({'INFO'}, "没有可处理的物体")
            elif total_removed > 0:
                self.report({'INFO'},
                           f"已处理 {processed} 个物体，删除 {total_removed} 个无效形态键，保留 {total_kept} 个有效形态键")
            else:
                self.report({'INFO'}, f"已处理 {processed} 个物体，所有形态键均有效，无需清理")

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

class XQFA_OT_ApplyAsShapekey(bpy.types.Operator):
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

classes = (
    XqfaShapeKeyPairItem,
    XqfaShapeKeyMappingItem,
    SKPairList,
    DATA_PT_shape_key_tools,
    O_ShapeKeysMatchRename,
    O_ShapeKeyMappingRemove,
    O_ShapeKeyMappingApply,
    O_ShapeKeyMappingReorder,
    O_ShapeKeysSortMatch,
    O_ShapeKeysRenameByOrder,
    O_ShapeKeysSelectAffectedVertices,
    O_ShapeKeysClean,
    O_ShapeKeysTransfer,
    XQFA_OT_ApplyAsShapekey,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.xqfa_shape_key_mappings = bpy.props.CollectionProperty(
        type=XqfaShapeKeyMappingItem,
        name="形态键映射记录",
    )

    bpy.types.Scene.sk_source_mesh = PointerProperty(
        description="选择编辑形态键的物体",
        type=bpy.types.Object, 
        poll=XQFA_Utils.is_mesh
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    if hasattr(bpy.types.Scene, 'xqfa_shape_key_mappings'):
        del bpy.types.Scene.xqfa_shape_key_mappings

    del bpy.types.Scene.sk_source_mesh