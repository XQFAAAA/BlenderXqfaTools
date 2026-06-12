# type: ignore
import bpy


def _get_unique_materials(obj):
    """从对象材质槽中收集去重后的材质列表（按出现顺序）"""
    result = []
    seen = set()
    for mat_slot in obj.material_slots:
        mat = mat_slot.material
        if mat and mat.name not in seen:
            seen.add(mat.name)
            result.append(mat)
    return result


def sync_material_list(scene, obj):
    """对比并同步材质列表。当对象或材质变化时重建；保留已有项的选中状态"""
    props = scene.material_batch_rename_props
    if not obj or obj.type != 'MESH':
        if len(props.material_items) > 0:
            props.material_items.clear()
        return

    current_mats = _get_unique_materials(obj)
    current_names = [mat.name for mat in current_mats]
    stored_names = [item.name for item in props.material_items]

    # 已匹配，无需重建
    if current_names == stored_names:
        return

    # 保留已有项的选中状态映射
    selected_map = {item.original_name: item.selected for item in props.material_items}
    props.material_items.clear()

    for mat in current_mats:
        item = props.material_items.add()
        item.name = mat.name
        item.original_name = mat.name
        item.selected = selected_map.get(mat.name, True)


def _on_depsgraph_update(scene, depsgraph):
    """depsgraph 变更后自动同步当前对象的材质列表（轻量缓存避免重复重建）"""
    obj = None
    for view_layer in scene.view_layers:
        obj = view_layer.objects.active
        if obj is not None:
            break
    if obj is None or obj.type != 'MESH':
        props = scene.material_batch_rename_props
        if len(props.material_items) > 0:
            props.material_items.clear()
        return
    sync_material_list(scene, obj)


def _on_load_post(dummy):
    """文件加载后同步活动对象的材质列表"""
    scene = bpy.context.scene
    if scene is None:
        return
    obj = bpy.context.active_object
    if obj is not None and obj.type == 'MESH':
        sync_material_list(scene, obj)


class XQFA_MaterialRenameItem(bpy.types.PropertyGroup):
    """材质批量重命名的列表项"""
    name: bpy.props.StringProperty()
    selected: bpy.props.BoolProperty(default=True)
    original_name: bpy.props.StringProperty()


class XQFA_OT_material_select(bpy.types.Operator):
    """点击材质项切换选中状态，支持 Shift 范围选和 Ctrl 切换选"""
    bl_idname = "xqfa.material_select"
    bl_label = "选择材质"
    bl_options = {'REGISTER', 'INTERNAL', 'UNDO'}

    index: bpy.props.IntProperty()

    def invoke(self, context, event):
        props = context.scene.material_batch_rename_props
        items = props.material_items
        if not items or self.index >= len(items):
            return {'CANCELLED'}

        if event.shift:
            start = min(props.last_selected_index, self.index)
            end = max(props.last_selected_index, self.index)
            for i in range(start, end + 1):
                items[i].selected = True
        elif event.ctrl:
            items[self.index].selected = not items[self.index].selected
            props.last_selected_index = self.index
        else:
            for i, item in enumerate(items):
                item.selected = (i == self.index)
            props.last_selected_index = self.index

        return {'FINISHED'}


class XQFA_OT_select_all_materials(bpy.types.Operator):
    """全选材质"""
    bl_idname = "xqfa.select_all_materials"
    bl_label = "全选"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        props = context.scene.material_batch_rename_props
        for item in props.material_items:
            item.selected = True
        return {'FINISHED'}


class XQFA_OT_deselect_all_materials(bpy.types.Operator):
    """取消全选材质"""
    bl_idname = "xqfa.deselect_all_materials"
    bl_label = "取消"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        props = context.scene.material_batch_rename_props
        for item in props.material_items:
            item.selected = False
        return {'FINISHED'}


class XQFA_OT_invert_material_selection(bpy.types.Operator):
    """反选材质"""
    bl_idname = "xqfa.invert_material_selection"
    bl_label = "反选"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        props = context.scene.material_batch_rename_props
        for item in props.material_items:
            item.selected = not item.selected
        return {'FINISHED'}


class XQFA_OT_batch_rename_materials(bpy.types.Operator):
    """对选中的材质执行查找替换"""
    bl_idname = "xqfa.batch_rename_materials"
    bl_label = "查找替换"
    bl_options = {'REGISTER', 'UNDO'}

    search_text: bpy.props.StringProperty(
        name="查找",
        description="要查找并替换的文本",
        default=""
    )
    replace_text: bpy.props.StringProperty(
        name="替换为",
        description="替换后的文本",
        default=""
    )
    use_case_insensitive: bpy.props.BoolProperty(
        name="忽略大小写",
        description="匹配时忽略大小写",
        default=False
    )

    @classmethod
    def poll(cls, context):
        props = context.scene.material_batch_rename_props
        return any(item.selected for item in props.material_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "search_text")
        col.prop(self, "replace_text")
        layout.prop(self, "use_case_insensitive", toggle=True)

    def execute(self, context):
        props = context.scene.material_batch_rename_props
        search_text = self.search_text
        replace_text = self.replace_text

        if not search_text:
            self.report({'WARNING'}, "查找内容为空")
            return {'CANCELLED'}

        renamed_count = 0
        for item in props.material_items:
            if not item.selected:
                continue
            mat = bpy.data.materials.get(item.original_name)
            if mat is None:
                mat = bpy.data.materials.get(item.name)
            if mat is None:
                continue

            old_name = mat.name
            if self.use_case_insensitive:
                import re
                pattern = re.compile(re.escape(search_text), re.IGNORECASE)
                new_name = pattern.sub(replace_text, old_name)
            else:
                new_name = old_name.replace(search_text, replace_text)

            if new_name != old_name:
                mat.name = new_name
                item.name = new_name
                item.original_name = new_name
                renamed_count += 1
                print(f"重命名材质: '{old_name}' -> '{new_name}'")

        self.report({'INFO'}, f"成功重命名 {renamed_count} 个材质")
        return {'FINISHED'}


class XQFA_OT_add_affix(bpy.types.Operator):
    """对选中的材质名添加前缀和/或后缀"""
    bl_idname = "xqfa.add_material_affix"
    bl_label = "前缀/后缀"
    bl_options = {'REGISTER', 'UNDO'}

    prefix_text: bpy.props.StringProperty(
        name="前缀",
        description="要添加的前缀文本",
        default=""
    )
    suffix_text: bpy.props.StringProperty(
        name="后缀",
        description="要添加的后缀文本",
        default=""
    )

    @classmethod
    def poll(cls, context):
        props = context.scene.material_batch_rename_props
        return any(item.selected for item in props.material_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "prefix_text")
        col.prop(self, "suffix_text")

    def execute(self, context):
        props = context.scene.material_batch_rename_props
        prefix = self.prefix_text
        suffix = self.suffix_text
        if not prefix and not suffix:
            self.report({'WARNING'}, "前缀和后缀都为空")
            return {'CANCELLED'}

        renamed_count = 0
        for item in props.material_items:
            if not item.selected:
                continue
            mat = bpy.data.materials.get(item.original_name)
            if mat is None:
                mat = bpy.data.materials.get(item.name)
            if mat is None:
                continue
            old_name = mat.name
            mat.name = f"{prefix}{old_name}{suffix}"
            item.name = mat.name
            item.original_name = mat.name
            renamed_count += 1

        self.report({'INFO'}, f"已为 {renamed_count} 个材质修改名称")
        return {'FINISHED'}


def _get_source_material(context):
    """获取当前活动材质（优先从节点编辑器获取，其次从活动材质槽）"""
    # 从 NODE_EDITOR 的空间获取正在编辑的材质
    for area in context.screen.areas:
        if area.type == 'NODE_EDITOR':
            for space in area.spaces:
                if space.type == 'NODE_EDITOR' and hasattr(space, 'node_tree'):
                    nt = space.node_tree
                    if nt and hasattr(nt, 'is_embedded_data') and nt.is_embedded_data:
                        mat = bpy.data.materials.get(nt.name)
                        if mat and mat.node_tree == nt:
                            return mat
    # 回退：从活动对象的活动材质槽获取
    obj = context.active_object
    if obj and obj.type == 'MESH' and obj.active_material:
        return obj.active_material
    return None


def _copy_rna_props(src, dst, skip_keys=None):
    """将 src 节点的属性复制到 dst 节点（基于 RNA 枚举）"""
    if skip_keys is None:
        skip_keys = set()
    for prop in src.bl_rna.properties:
        if prop.is_readonly or prop.identifier in skip_keys:
            continue
        prop_id = prop.identifier
        try:
            setattr(dst, prop_id, getattr(src, prop_id))
        except (AttributeError, TypeError):
            continue


def _copy_selected_nodes(src_mat, dst_mat):
    """将 src_mat 节点树中选中的节点复制到 dst_mat 的节点树，返回复制的节点数"""
    if src_mat is None or dst_mat is None or src_mat == dst_mat:
        return 0
    if not src_mat.node_tree:
        return 0

    # 确保目标材质有节点树
    if not dst_mat.node_tree:
        dst_mat.use_nodes = True

    src_tree = src_mat.node_tree
    dst_tree = dst_mat.node_tree

    # 收集选中的节点
    selected_nodes = [n for n in src_tree.nodes if n.select]
    if not selected_nodes:
        return 0

    # 构建节点映射（源节点 -> 目标节点）
    node_mapping = {}

    for src_node in selected_nodes:
        # 创建新节点
        try:
            new_node = dst_tree.nodes.new(type=src_node.bl_idname)
        except RuntimeError:
            continue

        # 复制通用属性
        _copy_rna_props(
            src_node, new_node,
            skip_keys={'bl_idname', 'bl_static_type', 'internal_links',
                       'inputs', 'outputs', 'select'}
        )

        # 特殊处理：节点组需要额外设置 node_tree
        if src_node.bl_idname == 'ShaderNodeGroup' and hasattr(src_node, 'node_tree') and src_node.node_tree:
            try:
                new_node.node_tree = src_node.node_tree
            except (AttributeError, RuntimeError):
                pass

        # 特殊处理：节点组的内部 sockets 名称/标签
        # （在 ShaderNodeGroup 中新 node 会自动根据 node_tree 生成 sockets）

        # 设置位置（覆盖可能从 rna 属性复制的值）
        new_node.location = src_node.location
        new_node.width = src_node.width
        new_node.height = src_node.height
        new_node.mute = src_node.mute
        new_node.hide = src_node.hide
        new_node.label = src_node.label
        new_node.name = src_node.name

        # 处理节点内部每个 socket 的默认值
        for i, src_socket in enumerate(src_node.inputs):
            if i >= len(new_node.inputs):
                break
            dst_socket = new_node.inputs[i]
            # 复制默认值（如果 socket 有 'default_value' 属性且可写）
            if hasattr(src_socket, 'default_value') and hasattr(dst_socket, 'default_value'):
                try:
                    if dst_socket.bl_rna.properties.get('default_value') and not dst_socket.bl_rna.properties['default_value'].is_readonly:
                        dst_socket.default_value = src_socket.default_value
                except (AttributeError, TypeError, RuntimeError):
                    pass

        node_mapping[src_node] = new_node

    # 复制节点之间的连线（仅在复制节点之间，且保留原线的 mute 状态）
    for src_link in src_tree.links:
        if src_link.from_node in node_mapping and src_link.to_node in node_mapping:
            # 找出对应的 sockets 索引
            from_node = node_mapping[src_link.from_node]
            to_node = node_mapping[src_link.to_node]

            # 用 socket 在节点中的索引匹配
            try:
                from_idx = list(src_link.from_node.outputs).index(src_link.from_socket)
                to_idx = list(src_link.to_node.inputs).index(src_link.to_socket)
            except ValueError:
                continue

            if from_idx >= len(from_node.outputs) or to_idx >= len(to_node.inputs):
                continue

            new_link = dst_tree.links.new(
                from_node.outputs[from_idx],
                to_node.inputs[to_idx],
                verify_limits=False
            )
            if hasattr(src_link, 'is_muted'):
                new_link.is_muted = src_link.is_muted

    return len(node_mapping)


class XQFA_OT_copy_nodes_to_materials(bpy.types.Operator):
    """将当前活动材质节点树中选中的节点复制到所有选中的材质"""
    bl_idname = "xqfa.copy_nodes_to_materials"
    bl_label = "复制选中节点到材质"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.material_batch_rename_props
        # 有勾选的材质项
        if not any(item.selected for item in props.material_items):
            return False
        # 有源材质
        src_mat = _get_source_material(context)
        if src_mat is None or not src_mat.node_tree:
            return False
        return any(n.select for n in src_mat.node_tree.nodes)

    def execute(self, context):
        props = context.scene.material_batch_rename_props
        src_mat = _get_source_material(context)

        if src_mat is None or not src_mat.node_tree:
            self.report({'WARNING'}, "找不到活动材质，或活动材质无节点树")
            return {'CANCELLED'}

        selected_nodes = [n for n in src_mat.node_tree.nodes if n.select]
        if not selected_nodes:
            self.report({'WARNING'}, "在活动材质中没有选中的节点")
            return {'CANCELLED'}

        target_count = 0
        total_nodes = 0
        for item in props.material_items:
            if not item.selected:
                continue
            dst_mat = bpy.data.materials.get(item.name)
            if dst_mat is None or dst_mat == src_mat:
                continue
            n = _copy_selected_nodes(src_mat, dst_mat)
            if n > 0:
                total_nodes += n
                target_count += 1

        if target_count == 0:
            self.report({'WARNING'}, "没有可作为目标的选中材质")
            return {'CANCELLED'}

        self.report({'INFO'}, f"已复制 {len(selected_nodes)} 个节点到 {target_count} 个材质（共 {total_nodes} 节点）")
        return {'FINISHED'}


def _delete_matched_nodes(src_mat, dst_mat):
    """从 dst_mat 中删除与 src_mat 选中节点同名的节点，返回删除数量"""
    if src_mat is None or dst_mat is None or src_mat == dst_mat:
        return 0
    if not src_mat.node_tree or not dst_mat.node_tree:
        return 0

    # 收集源材质中选中节点的名称集合
    src_selected_names = {n.name for n in src_mat.node_tree.nodes if n.select}
    if not src_selected_names:
        return 0

    dst_tree = dst_mat.node_tree
    deleted = 0
    # 收集待删除节点（不在遍历时删除，避免迭代器问题）
    to_remove = [n for n in dst_tree.nodes if n.name in src_selected_names]
    for n in to_remove:
        try:
            dst_tree.nodes.remove(n)
            deleted += 1
        except (RuntimeError, TypeError):
            continue
    return deleted


class XQFA_OT_delete_nodes_from_materials(bpy.types.Operator):
    """将与活动材质选中节点同名的节点从所有选中材质中删除"""
    bl_idname = "xqfa.delete_nodes_from_materials"
    bl_label = "从材质中删除选中节点"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.material_batch_rename_props
        if not any(item.selected for item in props.material_items):
            return False
        src_mat = _get_source_material(context)
        if src_mat is None or not src_mat.node_tree:
            return False
        return any(n.select for n in src_mat.node_tree.nodes)

    def execute(self, context):
        props = context.scene.material_batch_rename_props
        src_mat = _get_source_material(context)

        if src_mat is None or not src_mat.node_tree:
            self.report({'WARNING'}, "找不到活动材质，或活动材质无节点树")
            return {'CANCELLED'}

        selected_nodes = [n for n in src_mat.node_tree.nodes if n.select]
        if not selected_nodes:
            self.report({'WARNING'}, "在活动材质中没有选中的节点")
            return {'CANCELLED'}

        target_count = 0
        total_deleted = 0
        for item in props.material_items:
            if not item.selected:
                continue
            dst_mat = bpy.data.materials.get(item.name)
            if dst_mat is None or dst_mat == src_mat:
                continue
            n = _delete_matched_nodes(src_mat, dst_mat)
            if n > 0:
                total_deleted += n
                target_count += 1

        if target_count == 0:
            self.report({'WARNING'}, "没有可作为目标的选中材质，或目标材质中无匹配节点")
            return {'CANCELLED'}

        self.report({'INFO'}, f"已从 {target_count} 个材质中删除共 {total_deleted} 个节点")
        return {'FINISHED'}


class XQFA_MaterialBatchRenameProps(bpy.types.PropertyGroup):
    """材质批量重命名面板属性"""
    material_items: bpy.props.CollectionProperty(type=XQFA_MaterialRenameItem)
    last_selected_index: bpy.props.IntProperty(default=0)


class XQFA_PT_material_batch_rename(bpy.types.Panel):
    bl_label = "材质批量"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        props = context.scene.material_batch_rename_props
        obj = context.active_object

        if obj:
            layout.label(text=f"{obj.name}", icon='MESH_DATA')
        else:
            layout.label(text="未选择对象", icon='MESH_DATA')

        box = layout.box()
        row = box.row(align=True)
        row.operator("xqfa.batch_rename_materials", text=" ", icon='ZOOM_SELECTED')
        row.operator("xqfa.add_material_affix", text=" ", icon='SORTALPHA')
        row.operator("xqfa.copy_nodes_to_materials", text=" ", icon='PASTEDOWN')
        row.operator("xqfa.delete_nodes_from_materials", text=" ", icon='X')
        row.operator("xqfa.select_all_materials", text=" ", icon='CHECKBOX_HLT')
        row.operator("xqfa.deselect_all_materials", text=" ", icon='CHECKBOX_DEHLT')
        row.operator("xqfa.invert_material_selection", text=" ", icon='ARROW_LEFTRIGHT')

        if props.material_items:
            col = box.column(align=True)
            for i, item in enumerate(props.material_items):
                op = col.operator(
                    "xqfa.material_select",
                    text=item.name,
                    icon='MATERIAL',
                    depress=item.selected,
                )
                op.index = i
        else:
            box.label(text="当前对象没有材质", icon='INFO')


classes = (
    XQFA_MaterialRenameItem,
    XQFA_MaterialBatchRenameProps,
    XQFA_OT_material_select,
    XQFA_OT_select_all_materials,
    XQFA_OT_deselect_all_materials,
    XQFA_OT_invert_material_selection,
    XQFA_OT_batch_rename_materials,
    XQFA_OT_add_affix,
    XQFA_OT_copy_nodes_to_materials,
    XQFA_OT_delete_nodes_from_materials,
    XQFA_PT_material_batch_rename,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.material_batch_rename_props = bpy.props.PointerProperty(
        type=XQFA_MaterialBatchRenameProps
    )
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    del bpy.types.Scene.material_batch_rename_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
