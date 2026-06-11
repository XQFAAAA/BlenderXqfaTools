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
    """depsgraph 变更后自动同步当前对象的材质列表"""
    obj = None
    for view_layer in scene.view_layers:
        obj = view_layer.objects.active
        if obj is not None:
            break
    if obj is None or obj.type != 'MESH':
        return
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


class XQFA_MaterialBatchRenameProps(bpy.types.PropertyGroup):
    """材质批量重命名面板属性"""
    material_items: bpy.props.CollectionProperty(type=XQFA_MaterialRenameItem)
    last_selected_index: bpy.props.IntProperty(default=0)


class XQFA_PT_material_batch_rename(bpy.types.Panel):
    bl_label = "材质批量重命名"
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

        sync_material_list(context.scene, obj)

        layout.label(text=f"{obj.name}", icon='MESH_DATA')

        box = layout.box()
        row = box.row(align=True)
        row.operator("xqfa.batch_rename_materials", text=" ", icon='ZOOM_SELECTED')
        row.operator("xqfa.add_material_affix", text=" ", icon='SORTALPHA')
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
    XQFA_PT_material_batch_rename,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.material_batch_rename_props = bpy.props.PointerProperty(
        type=XQFA_MaterialBatchRenameProps
    )
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)


def unregister():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    del bpy.types.Scene.material_batch_rename_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
