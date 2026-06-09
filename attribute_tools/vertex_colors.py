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

# 调色板颜色项
class PaletteColorItem(PropertyGroup):
    color: FloatVectorProperty(
        name="颜色",
        subtype='COLOR_GAMMA',# 使用 COLOR_GAMMA 而不是 COLOR
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0)
    )

class DATA_PT_color_attribute_tools(bpy.types.Panel):
    bl_idname = "X_PT_ColorAttributeTools"
    bl_label = "顶点色"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'
    
    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了此子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'AttributeTools'
   

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # 颜色属性管理
        col = layout.column(align=True)
        
        # 添加顶点色层操作按钮
        row = col.row(align=True)
        row.prop(scene, "color_attr_target_index", text="")
        row.operator(O_SetActiveColorAttributes.bl_idname, text="", icon="RESTRICT_SELECT_OFF")
        row.operator(O_SetRenderColorAttributes.bl_idname, text="", icon="RESTRICT_RENDER_OFF")
        row.operator(O_RemoveColorAttributes.bl_idname, text="", icon="TRASH")
        row.operator(O_AddAndRenameColorAttributes.bl_idname, text="", icon='SORTALPHA')
        row.operator(O_ConvertColorAttributeType.bl_idname, text="", icon='UV_SYNC_SELECT')

        # 添加颜色按钮
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator(O_AddColor.bl_idname, text="添加颜色", icon='ADD')
        
        # 调色板颜色列表
        for i, color_item in enumerate(scene.palette_colors):
            row = col.row(align=True)
            row.prop(color_item, "color", text="")
            
            # 应用颜色按钮
            op = row.operator(O_ApplyColor.bl_idname, text="", icon='BRUSH_DATA')
            op.color_index = i

            # 删除颜色按钮
            op = row.operator(O_RemoveColor.bl_idname, text="", icon='X')
            op.color_index = i
        


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
            
            # 使用 color_attributes 获取所有类型的颜色属性
            color_attrs = obj.data.color_attributes
            
            if target_index < 0 or target_index >= len(color_attrs):
                self.report({'WARNING'}, f"物体 {obj.name} 的颜色属性索引 {target_index} 超出范围")
                continue

            color_attrs.active_color_index = target_index
            
            
            
            set_active_count += 1
        
        # 强制刷新所有区域
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
        
        # 强制刷新所有区域
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
            # 使用 color_attributes 获取所有类型的颜色属性，参考 O_SetActiveColorAttributes
            color_attrs = obj.data.color_attributes
            
            if target_index < 0 or target_index >= len(color_attrs):
                self.report({'WARNING'}, f"物体 {obj.name} 的索引 {target_index} 超出范围")
                continue
            
            # 获取目标属性对象
            attr_to_remove = color_attrs[target_index]
            attr_name = attr_to_remove.name
            
            # 执行删除
            color_attrs.remove(attr_to_remove)
            removed_colors += 1
            
        # 强制刷新所有区域
        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"处理完成: {processed_objects}个物体, 删除了索引为 {target_index} 的属性层")
        return {'FINISHED'}

class O_AddAndRenameColorAttributes(bpy.types.Operator):
    bl_idname = "xqfa.color_attr_add_rename"
    bl_label = "添加并重命名序列"
    bl_description = "确保顶点色层数足够，并统一重命名为 COLOR, COLOR1, COLOR2..."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        target_index = scene.color_attr_target_index
        processed_objects = 0

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            processed_objects += 1
            mesh = obj.data
            
            # 1. 如果层数不足，添加新层 (默认使用字节颜色和面角)
            current_count = len(mesh.color_attributes)
            if current_count < target_index + 1:
                for j in range(current_count, target_index + 1):
                    mesh.color_attributes.new(
                        name="TEMP",
                        type='BYTE_COLOR',
                        domain='CORNER'
                    )

            # 4. 统一重命名
            # 先重命名数字，避免重名
            for k, attr in enumerate(mesh.color_attributes):
                new_name = f"{k}"
                attr.name = new_name
            for k, attr in enumerate(mesh.color_attributes):
                new_name = f"COLOR{k}" if k > 0 else "COLOR"
                attr.name = new_name

        
        # 刷新 UI
        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'},f"完成: {processed_objects}个物体")
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
            
            # 1. 预先记录所有属性的原始名称
            attr_names = [attr.name for attr in mesh.color_attributes]
            
            # 2. 按名称查找并转换
            for name in attr_names:
                # 重新在当前的 color_attributes 中查找该名称对应的索引
                # 因为转换过程中索引可能会发生变动，所以每次循环都重新获取索引
                idx = mesh.color_attributes.find(name)
                
                if idx != -1:
                    # 获取属性对象进行判断
                    attr = mesh.color_attributes[idx]
                    
                    # 如果类型和域已经符合要求，则跳过
                    if attr.domain == self.domain_enum and attr.data_type == self.data_type_enum:
                        continue
                    
                    # 关键修改：显式指定 active_color_index
                    mesh.color_attributes.active_color_index = idx
                    
                    # 执行转换
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


# 调色板操作
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
        
        # 获取调色板颜色（转换为0-1范围的RGBA）
        color_item = scene.palette_colors[self.color_index]
        color = color_item.color
        
        processed_objects = 0
        applied_count = 0
        
        # 遍历所有选中的物体
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
                
            processed_objects += 1
            
            # 检查顶点色层
            mesh = obj.data
            if not mesh.vertex_colors:
                self.report({'WARNING'}, f"物体 {obj.name} 没有顶点色层")
                continue
                
            if not mesh.vertex_colors.active:
                self.report({'WARNING'}, f"物体 {obj.name} 没有激活的顶点色层")
                continue
            
            # 使用bmesh高效修改
            bm = bmesh.new()
            bm.from_mesh(mesh)
            
            # 获取激活的顶点色层
            color_layer = mesh.vertex_colors.active
            color_layer_bm = bm.loops.layers.color.get(color_layer.name)
            
            if not color_layer_bm:
                bm.free()
                self.report({'WARNING'}, f"无法访问物体 {obj.name} 的顶点色层数据")
                continue
            
            # 应用颜色到所有顶点
            for face in bm.faces:
                for loop in face.loops:
                    loop[color_layer_bm] = color
            
            # 更新网格
            bm.to_mesh(mesh)
            bm.free()
            applied_count += 1
        
        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        
        self.report({'INFO'}, 
                   f"颜色 '{color_item.name}' 应用到 {applied_count}/{processed_objects} 个物体的活动顶点色层")
        return {'FINISHED'}

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
    O_ApplyColor
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
    
    bpy.types.Scene.palette_colors = CollectionProperty(
        type=PaletteColorItem
    )

    # 延迟添加默认颜色
    def add_default_colors():
        # 确保在正确的上下文中
        if hasattr(bpy.context, 'scene'):
            scene = bpy.context.scene
            # 只在调色板为空时添加默认颜色
            if len(scene.palette_colors) == 0:
                green = scene.palette_colors.add()
                green.color = (0.0, 0.352, 0.0, 1.0)
                
                orange = scene.palette_colors.add()
                orange.color = (1.0, 0.352, 0.0, 1.0)
                
                black = scene.palette_colors.add()
                black.color = (0.0, 0.0, 0.0, 1.0)
    
    # 使用计时器延迟执行，确保在正确的上下文中
    bpy.app.timers.register(add_default_colors, first_interval=0.1)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.color_attr_target_index
    del bpy.types.Scene.palette_colors