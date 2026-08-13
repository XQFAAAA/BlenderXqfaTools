# type: ignore
import bpy
import re


# --- 重命名工具子面板 ---

class XQFA_PT_RenameTools(bpy.types.Panel):
    bl_label = "重命名工具"
    bl_idname = "XQFA_PT_rename_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了此子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'OtherTools'

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        op = row.operator(XQFA_OT_AddNameAffix.bl_idname, text="前缀", icon="OUTLINER_OB_FONT")
        op.mode = 'PREFIX'
        op = row.operator(XQFA_OT_AddNameAffix.bl_idname, text="后缀", icon="OUTLINER_OB_FONT")
        op.mode = 'SUFFIX'
        col = layout.column()
        col.operator(XQFA_OT_ObjectNameToMaterial.bl_idname, icon="SYNTAX_ON")
        col.operator(XQFA_OT_MaterialToObjectName.bl_idname, icon="SYNTAX_OFF")
        col.operator(XQFA_OT_SearchReplaceObjectName.bl_idname, icon='FONT_DATA')


# --- 算子 (Operators) ---

class XQFA_OT_AddNameAffix(bpy.types.Operator):
    """为选中物体的名称添加前缀或后缀，同时也对每个物体的材质名执行相同操作"""
    bl_idname = "xqfa.add_name_affix"
    bl_label = "添加名称前后缀"
    bl_description = "为选中物体的名称添加前缀或后缀，同时对选中物体的材质名也执行相同操作"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="模式",
        description="添加前缀还是后缀",
        items=[
            ('PREFIX', "前缀", "在名称前添加前缀"),
            ('SUFFIX', "后缀", "在名称后添加后缀"),
        ],
        default='PREFIX',
    )

    prefix: bpy.props.StringProperty(
        name="前缀",
        description="要添加到名称前面的前缀文本",
        default="Component ",
    )

    suffix: bpy.props.StringProperty(
        name="后缀",
        description="要添加到名称后面的后缀文本",
        default="",
    )

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        if self.mode == 'PREFIX':
            layout.prop(self, "prefix")
        else:
            layout.prop(self, "suffix")

    def execute(self, context):
        selected_objects = context.selected_objects

        if not selected_objects:
            self.report({'WARNING'}, "未选择任何物体")
            return {'CANCELLED'}

        is_prefix = self.mode == 'PREFIX'
        affix = self.prefix if is_prefix else self.suffix
        kind = "前缀" if is_prefix else "后缀"

        if not affix:
            self.report({'WARNING'}, f"{kind}不能为空")
            return {'CANCELLED'}

        rename_object_count = 0
        rename_material_count = 0

        for obj in selected_objects:
            old_name = obj.name
            if is_prefix:
                already = old_name.startswith(affix)
                new_name = f"{affix}{old_name}"
            else:
                already = old_name.endswith(affix)
                new_name = f"{old_name}{affix}"

            if already:
                print(f"Skipped Object '{old_name}' (已包含该{kind})")
                continue

            obj.name = new_name
            rename_object_count += 1
            print(f"Renamed Object '{old_name}' -> '{new_name}'")

            # 对物体上的所有材质名执行相同操作
            if obj.type == 'MESH' and obj.data.materials:
                for mat in obj.data.materials:
                    if mat is None:
                        continue
                    old_mat_name = mat.name
                    if is_prefix:
                        mat_already = old_mat_name.startswith(affix)
                        new_mat_name = f"{affix}{old_mat_name}"
                    else:
                        mat_already = old_mat_name.endswith(affix)
                        new_mat_name = f"{old_mat_name}{affix}"
                    if mat_already:
                        print(f"Skipped Material '{old_mat_name}' (已包含该{kind})")
                        continue
                    mat.name = new_mat_name
                    rename_material_count += 1
                    print(f"Renamed Material '{old_mat_name}' -> '{new_mat_name}'")

        self.report({'INFO'}, f"成功重命名 {rename_object_count} 个物体, {rename_material_count} 个材质")
        return {'FINISHED'}


class XQFA_OT_ObjectNameToMaterial(bpy.types.Operator):
    """将唯一材质的名称改为物体名称"""
    bl_idname = "xqfa.object_name_to_material"
    bl_label = "物体名称-->材质名称"
    bl_description = "对所有选中的网格物体，若材质唯一则将材质名改为物体名"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and any(
            obj.type == 'MESH' and obj.data.materials for obj in context.selected_objects
        )

    def execute(self, context):
        mesh_objs = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not mesh_objs:
            self.report({'WARNING'}, "未选中任何网格物体")
            return {'CANCELLED'}

        renamed_count = 0
        for obj in mesh_objs:
            mats = [m for m in obj.data.materials if m is not None]
            if len(mats) != 1:
                continue
            mat = mats[0]
            if mat.name != obj.name:
                mat.name = obj.name
                renamed_count += 1

        self.report({'INFO'}, f"已重命名 {renamed_count} 个材质")
        return {'FINISHED'}


class XQFA_OT_MaterialToObjectName(bpy.types.Operator):
    """将物体名称改为其唯一材质的名称"""
    bl_idname = "xqfa.material_to_object_name"
    bl_label = "材质名称-->物体名称"
    bl_description = "对所有选中的网格物体，若材质唯一则将物体名改为材质名"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and any(
            obj.type == 'MESH' and obj.data.materials for obj in context.selected_objects
        )

    def execute(self, context):
        mesh_objs = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not mesh_objs:
            self.report({'WARNING'}, "未选中任何网格物体")
            return {'CANCELLED'}

        renamed_count = 0
        for obj in mesh_objs:
            mats = [m for m in obj.data.materials if m is not None]
            if len(mats) != 1:
                continue
            mat_name = mats[0].name
            if obj.name != mat_name:
                obj.name = mat_name
                renamed_count += 1

        self.report({'INFO'}, f"已重命名 {renamed_count} 个物体")
        return {'FINISHED'}


class XQFA_OT_SearchReplaceObjectName(bpy.types.Operator):
    """对选中物体的名称进行搜索替换"""
    bl_idname = "xqfa.search_replace_object_name"
    bl_label = "物体名称搜索替换"
    bl_description = "对所有选中物体的名称进行搜索替换操作"
    bl_options = {'REGISTER', 'UNDO'}

    search_text: bpy.props.StringProperty(
        name="搜索",
        description="要搜索的文本",
        default=""
    )

    replace_text: bpy.props.StringProperty(
        name="替换",
        description="替换为的文本",
        default=""
    )

    use_regex: bpy.props.BoolProperty(
        name="正则表达式",
        description="使用正则表达式进行搜索",
        default=False
    )

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and len(context.selected_objects) > 0

    def invoke(self, context, event):
        if not self.search_text and context.active_object:
            self.search_text = context.active_object.name
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "search_text")
        layout.prop(self, "replace_text")
        layout.prop(self, "use_regex")

    def execute(self, context):
        if not self.search_text:
            self.report({'WARNING'}, "搜索内容为空")
            return {'CANCELLED'}

        renamed_count = 0
        for obj in context.selected_objects:
            old_name = obj.name
            if self.use_regex:
                new_name = re.sub(self.search_text, self.replace_text, old_name)
            else:
                new_name = old_name.replace(self.search_text, self.replace_text)
            if new_name != old_name:
                obj.name = new_name
                renamed_count += 1

        self.report({'INFO'}, f"已重命名 {renamed_count} 个物体")
        return {'FINISHED'}


classes = (
    XQFA_PT_RenameTools,
    XQFA_OT_AddNameAffix,
    XQFA_OT_ObjectNameToMaterial,
    XQFA_OT_MaterialToObjectName,
    XQFA_OT_SearchReplaceObjectName,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
