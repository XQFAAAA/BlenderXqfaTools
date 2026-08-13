# type: ignore
import bpy
import bmesh
from bpy.props import (StringProperty,
                       BoolProperty,
                       IntProperty,
                       FloatProperty,
                       FloatVectorProperty,
                       EnumProperty,
                       CollectionProperty)
from bpy.types import PropertyGroup


##########################
# Property Groups
##########################

class PaletteColorItem(PropertyGroup):
    color: FloatVectorProperty(
        name="颜色",
        subtype='COLOR_GAMMA',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0)
    )


##########################
# Operators
##########################

class O_SetActiveColorAttributes(bpy.types.Operator):
    bl_idname = "xqfa.color_attr_set_active"
    bl_label = "活动"
    bl_description = "将所有选中物体的活动颜色属性设置为指定索引（包含所有类型）"

    def execute(self, context):
        scene = context.scene
        target_index = scene.color_attr_target_index

        processed_objects = 0
        set_active_count = 0

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            processed_objects += 1
            color_attrs = obj.data.color_attributes
            if target_index < 0 or target_index >= len(color_attrs):
                self.report({'WARNING'}, f"物体 {obj.name} 的颜色属性索引 {target_index} 超出范围")
                continue
            color_attrs.active_color_index = target_index
            set_active_count += 1

        for area in context.screen.areas:
            area.tag_redraw()
        self.report({'INFO'}, f"完成: {processed_objects}个物体, 设置了{set_active_count}个活动颜色属性")
        return {'FINISHED'}


class O_SetRenderColorAttributes(bpy.types.Operator):
    bl_idname = "xqfa.color_attr_set_render"
    bl_label = "渲染"
    bl_description = "将所有选中物体的渲染顶点色层设置为指定索引"

    def execute(self, context):
        scene = context.scene
        target_index = scene.color_attr_target_index

        processed_objects = 0
        set_render_count = 0

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            processed_objects += 1
            color_attrs = obj.data.color_attributes
            if target_index < 0 or target_index >= len(color_attrs):
                self.report({'WARNING'}, f"物体 {obj.name} 的顶点色索引 {target_index} 超出范围")
                continue
            color_attrs.render_color_index = target_index
            set_render_count += 1

        for area in context.screen.areas:
            area.tag_redraw()
        self.report({'INFO'}, f"处理完成: {processed_objects}个物体, 设置了{set_render_count}个渲染顶点色层")
        return {'FINISHED'}


class O_RemoveColorAttributes(bpy.types.Operator):
    bl_idname = "xqfa.color_attr_remove"
    bl_label = "删除"
    bl_description = "删除指定索引的顶点色层 (支持所有颜色属性类型)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        target_index = scene.color_attr_target_index

        processed_objects = 0
        removed_colors = 0

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            processed_objects += 1
            color_attrs = obj.data.color_attributes
            if target_index < 0 or target_index >= len(color_attrs):
                self.report({'WARNING'}, f"物体 {obj.name} 的索引 {target_index} 超出范围")
                continue
            color_attrs.remove(color_attrs[target_index])
            removed_colors += 1

        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"处理完成: {processed_objects}个物体, 删除了索引为 {target_index} 的属性层")
        return {'FINISHED'}


class O_AddAndRenameColorAttributes(bpy.types.Operator):
    bl_idname = "xqfa.color_attr_add_rename"
    bl_label = "添加顶点色序列"
    bl_description = "在顶部添加 COLOR, COLOR1... 顶点色层，不覆盖不重命名已有层"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def _prepend_color_attributes(mesh, count):
        """在顶点色列表顶部添加count个新层，原有层顺序不变向下顺延"""
        color_attrs = mesh.color_attributes

        # 快照原有层（名称、域、数据类型、颜色数据）及活动/渲染索引
        original = [(a.name, a.domain, a.data_type, [d.color[:] for d in a.data]) for a in color_attrs]
        active_index = color_attrs.active_color_index
        render_index = getattr(color_attrs, 'render_color_index', -1)

        # 快照当前活动层的颜色数据，用于填充新增层（新增层内容与活动层相同）
        active_attr = color_attrs[active_index] if 0 <= active_index < len(original) else None
        active_data = [d.color[:] for d in active_attr.data] if active_attr else None
        active_domain = active_attr.domain if active_attr else 'CORNER'

        # 新层命名避免与原有层冲突
        used_names = {name for name, _, _, _ in original}
        new_names = []
        i = 0
        while len(new_names) < count:
            name = f"COLOR{i}" if i > 0 else "COLOR"
            if name not in used_names:
                used_names.add(name)
                new_names.append(name)
            i += 1

        # 1. 删除所有原有层（使列表清空，后续新层自然排在最前）
        for a in list(color_attrs):
            color_attrs.remove(a)

        # 2. 创建新层并复制活动层的颜色数据
        for name in new_names:
            new_layer = color_attrs.new(name=name, type='BYTE_COLOR', domain='CORNER')
            if new_layer is None:
                raise RuntimeError("创建顶点色失败：可能已达数量上限或网格没有面")
            if active_data is not None:
                if active_domain == 'CORNER':
                    for li, col in enumerate(active_data):
                        new_layer.data[li].color = col
                else:  # POINT 域：按顶点索引映射到面角
                    for li, loop in enumerate(mesh.loops):
                        new_layer.data[li].color = active_data[loop.vertex_index]

        # 3. 按原顺序重建原有层
        for src_name, src_domain, src_type, color_list in original:
            copied = color_attrs.new(name=src_name, type=src_type, domain=src_domain)
            if copied is None:
                raise RuntimeError("创建顶点色失败：可能已达数量上限或网格没有面")
            for li, col in enumerate(color_list):
                copied.data[li].color = col

        # 4. 恢复活动/渲染层（新增层在顶部，原索引整体下移 count 位）
        if original:
            color_attrs.active_color_index = active_index + count
            if render_index >= 0:
                color_attrs.render_color_index = render_index + count

    def execute(self, context):
        scene = context.scene
        target_index = scene.color_attr_target_index
        count = target_index + 1

        processed_objects = 0
        added_colors = 0

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            processed_objects += 1
            color_attrs = obj.data.color_attributes
            # Blender 每个网格最多 31 个顶点色（MAX_MTCOL 限制）
            if len(color_attrs) + count > 31:
                self.report({'WARNING'}, f"物体 {obj.name} 添加顶点色失败：Blender 每网格最多 31 个顶点色（当前 {len(color_attrs)} 个，还需 {count} 个）")
                continue
            try:
                self._prepend_color_attributes(obj.data, count)
            except RuntimeError as e:
                self.report({'WARNING'}, f"物体 {obj.name} 添加顶点色失败：{e}")
                continue
            added_colors += count

        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"处理完成: {processed_objects}个物体, 添加{added_colors}个")
        return {'FINISHED'}


class O_ConvertColorAttributeType(bpy.types.Operator):
    bl_idname = "xqfa.color_attr_convert_type"
    bl_label = "转换属性类型"
    bl_description = "根据名称识别并转换所有选中物体的顶点色层类型"
    bl_options = {'REGISTER', 'UNDO'}

    domain_enum: EnumProperty(
        name="域",
        items=[('POINT', "顶点 (Point)", ""), ('CORNER', "面角 (Face Corner)", "")],
        default='CORNER'
    )
    data_type_enum: EnumProperty(
        name="数据类型",
        items=[('FLOAT_COLOR', "颜色 (Linear)", ""), ('BYTE_COLOR', "字节颜色 (sRGB)", "")],
        default='BYTE_COLOR'
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        original_active = context.view_layer.objects.active
        processed_objects = 0

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            processed_objects += 1
            context.view_layer.objects.active = obj
            mesh = obj.data

            attr_names = [attr.name for attr in mesh.color_attributes]
            for name in attr_names:
                idx = mesh.color_attributes.find(name)
                if idx != -1:
                    attr = mesh.color_attributes[idx]
                    if attr.domain == self.domain_enum and attr.data_type == self.data_type_enum:
                        continue
                    mesh.color_attributes.active_color_index = idx
                    bpy.ops.geometry.color_attribute_convert(
                        domain=self.domain_enum,
                        data_type=self.data_type_enum
                    )

        context.view_layer.objects.active = original_active
        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"类型转换完成: {processed_objects}个物体")
        return {'FINISHED'}


class O_AddColor(bpy.types.Operator):
    bl_idname = "xqfa.color_attr_add_color"
    bl_label = "添加颜色"
    bl_description = "向调色板添加新颜色"

    def execute(self, context):
        scene = context.scene
        new_color = scene.palette_colors.add()
        new_color.name = f"颜色 {len(scene.palette_colors)}"
        new_color.color = (1, 1, 1, 1)
        return {'FINISHED'}


class O_RemoveColor(bpy.types.Operator):
    bl_idname = "xqfa.color_attr_remove_color"
    bl_label = "删除颜色"
    bl_description = "从调色板中删除颜色"

    color_index: IntProperty()

    def execute(self, context):
        scene = context.scene
        if scene.palette_colors:
            scene.palette_colors.remove(self.color_index)
        return {'FINISHED'}


class O_ApplyColor(bpy.types.Operator):
    bl_idname = "xqfa.color_attr_apply_color"
    bl_label = "应用颜色"
    bl_description = "将颜色应用到所有选中物体的活动顶点色层"

    color_index: IntProperty()

    def execute(self, context):
        scene = context.scene

        if self.color_index >= len(scene.palette_colors):
            self.report({'ERROR'}, "调色板颜色索引无效")
            return {'CANCELLED'}

        color_item = scene.palette_colors[self.color_index]
        color = color_item.color

        processed_objects = 0
        applied_count = 0

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            processed_objects += 1
            mesh = obj.data
            if not mesh.vertex_colors:
                self.report({'WARNING'}, f"物体 {obj.name} 没有顶点色层")
                continue
            if not mesh.vertex_colors.active:
                self.report({'WARNING'}, f"物体 {obj.name} 没有激活的顶点色层")
                continue

            bm = bmesh.new()
            bm.from_mesh(mesh)
            color_layer_bm = bm.loops.layers.color.get(mesh.vertex_colors.active.name)
            if not color_layer_bm:
                bm.free()
                self.report({'WARNING'}, f"无法访问物体 {obj.name} 的顶点色层数据")
                continue

            for face in bm.faces:
                for loop in face.loops:
                    loop[color_layer_bm] = color

            bm.to_mesh(mesh)
            bm.free()
            applied_count += 1

        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'},
                   f"颜色 '{color_item.name}' 应用到 {applied_count}/{processed_objects} 个物体的活动顶点色层")
        return {'FINISHED'}


##########################
# Panel
##########################

class DATA_PT_color_attribute_tools(bpy.types.Panel):
    bl_idname = "X_PT_ColorAttributeTools"
    bl_label = "顶点色"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'AttributeTools'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)

        row = col.row(align=True)
        row.prop(scene, "color_attr_target_index", text="")
        row.operator(O_SetActiveColorAttributes.bl_idname, text="", icon="RESTRICT_SELECT_OFF")
        row.operator(O_SetRenderColorAttributes.bl_idname, text="", icon="RESTRICT_RENDER_OFF")
        row.operator(O_RemoveColorAttributes.bl_idname, text="", icon="TRASH")
        row.operator(O_AddAndRenameColorAttributes.bl_idname, text="", icon='ADD')
        row.operator(O_ConvertColorAttributeType.bl_idname, text="", icon='UV_SYNC_SELECT')

        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator(O_AddColor.bl_idname, text="添加颜色", icon='ADD')

        for i, color_item in enumerate(scene.palette_colors):
            row = col.row(align=True)
            row.prop(color_item, "color", text="")
            op = row.operator(O_ApplyColor.bl_idname, text="", icon='BRUSH_DATA')
            op.color_index = i
            op = row.operator(O_RemoveColor.bl_idname, text="", icon='X')
            op.color_index = i


##########################
# Registration
##########################

classes = (
    PaletteColorItem,
    DATA_PT_color_attribute_tools,
    O_SetActiveColorAttributes,
    O_SetRenderColorAttributes,
    O_RemoveColorAttributes,
    O_AddAndRenameColorAttributes,
    O_ConvertColorAttributeType,
    O_AddColor,
    O_RemoveColor,
    O_ApplyColor,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.color_attr_target_index = IntProperty(
        name="目标顶点色索引",
        description="要设置的活动/渲染顶点色的索引",
        default=0,
        min=0,
        max=31
    )
    bpy.types.Scene.palette_colors = CollectionProperty(type=PaletteColorItem)

    def add_default_colors():
        if hasattr(bpy.context, 'scene'):
            scene = bpy.context.scene
            if len(scene.palette_colors) == 0:
                green = scene.palette_colors.add()
                green.color = (0.0, 0.352, 0.0, 1.0)
                orange = scene.palette_colors.add()
                orange.color = (1.0, 0.352, 0.0, 1.0)
                black = scene.palette_colors.add()
                black.color = (0.0, 0.0, 0.0, 1.0)

    bpy.app.timers.register(add_default_colors, first_interval=0.1)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.color_attr_target_index
    del bpy.types.Scene.palette_colors
