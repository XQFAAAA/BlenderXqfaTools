# type: ignore
import bpy
import blf
import bmesh
from bpy_extras.view3d_utils import location_3d_to_region_2d

# 绘制处理器
_draw_handle = None
_draw_handle_uv = None

def draw_shape_key_overlay(context):
    # 检查是否启用物体额外信息
    obj = context.active_object
    if not obj:
        return
    
    if hasattr(context.scene, "show_extra_object_info") and context.scene.show_extra_object_info:
        # --- 1. 绘制左下角的统计信息 (顶点组/形态键) ---
        draw_stat_info(context, obj)
    
    # --- 2. 绘制选中顶点的 ID (3D 锚点跟随) ---
    if hasattr(context.scene, "show_vertex_ids") and context.scene.show_vertex_ids:
        if obj.mode == 'EDIT' and obj.type == 'MESH':
            draw_vertex_ids(context, obj)
    
    # --- 3. 绘制选中顶点的面拐编号 ---
    if hasattr(context.scene, "show_loop_ids") and context.scene.show_loop_ids:
        if obj.mode == 'EDIT' and obj.type == 'MESH':
            draw_loop_ids(context, obj)

def draw_stat_info(context, obj):
    """绘制左下角的基础信息统计"""
    # 获取顶点组信息
    vertex_group_count = 0
    current_vertex_group = "无"
    if obj.vertex_groups:
        vertex_group_count = len(obj.vertex_groups)
        idx = obj.vertex_groups.active_index
        if 0 <= idx < vertex_group_count:
            current_vertex_group = obj.vertex_groups[idx].name
    
    vg_text = f"顶点组: {current_vertex_group} / {vertex_group_count}"
    
    # 获取形态键信息
    shape_key_count = 0
    current_shape_key = "无"
    if obj.type == 'MESH' and obj.data.shape_keys:
        shape_keys = obj.data.shape_keys
        shape_key_count = len(shape_keys.key_blocks)
        active_index = obj.active_shape_key_index
        if 0 <= active_index < shape_key_count:
            current_shape_key = shape_keys.key_blocks[active_index].name
    
    sk_text = f"形态键: {current_shape_key} / {shape_key_count}"
    
    font_id = 0
    blf.size(font_id, 12)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    
    # 绘制形态键 (靠下)
    blf.position(font_id, 50, 30, 0)
    blf.draw(font_id, sk_text)
    
    # 绘制顶点组 (靠上一点)
    blf.position(font_id, 50, 50, 0)
    blf.draw(font_id, vg_text)

def draw_vertex_ids(context, obj):
    """在 3D 视图中顶点位置绘制 ID"""
    bm = bmesh.from_edit_mesh(obj.data)
    
    font_id = 0
    blf.size(font_id, 18)
    blf.color(font_id, 0.0, 1.0, 0.8, 1.0)
    
    region = context.region
    rv3d = context.region_data
    matrix_world = obj.matrix_world

    # 只处理选中的顶点
    selected_verts = [v for v in bm.verts if v.select]
    
    for v in selected_verts:
        # 将顶点的局部坐标转换为世界坐标
        world_pos = matrix_world @ v.co
        # 将世界坐标转换为屏幕 2D 坐标
        screen_pos = location_3d_to_region_2d(region, rv3d, world_pos)
        
        if screen_pos:
            blf.position(font_id, screen_pos[0] + 5, screen_pos[1] + 5, 0)
            blf.draw(font_id, str(v.index))

def draw_loop_ids(context, obj):
    """在 3D 视图中顶点位置绘制面拐编号 (Loop Index)"""
    bm = bmesh.from_edit_mesh(obj.data)
    
    font_id = 0
    blf.size(font_id, 18)
    blf.color(font_id, 1.0, 0.6, 0.2, 1.0)
    
    region = context.region
    rv3d = context.region_data
    matrix_world = obj.matrix_world

    selected_verts = [v for v in bm.verts if v.select]
    
    for v in selected_verts:
        loop_indices = [loop.index for loop in v.link_loops]
        if not loop_indices:
            continue
        world_pos = matrix_world @ v.co
        screen_pos = location_3d_to_region_2d(region, rv3d, world_pos)
        if screen_pos:
            text = ",".join(map(str, loop_indices))
            blf.position(font_id, screen_pos[0] + 5, screen_pos[1] - 12, 0)
            blf.draw(font_id, text)

def draw_uv_overlay(context):
    obj = context.active_object
    if not obj:
        return
    if obj.mode != 'EDIT' or obj.type != 'MESH':
        return
    
    if hasattr(context.scene, "show_vertex_ids_uv") and context.scene.show_vertex_ids_uv:
        draw_vertex_ids_uv(context, obj)
    
    if hasattr(context.scene, "show_loop_ids_uv") and context.scene.show_loop_ids_uv:
        draw_loop_ids_uv(context, obj)

def draw_vertex_ids_uv(context, obj):
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        return
    
    font_id = 0
    blf.size(font_id, 18)
    blf.color(font_id, 0.0, 1.0, 0.8, 1.0)
    
    region = context.region
    view2d = region.view2d
    
    selected_verts = [v for v in bm.verts if v.select]
    
    for v in selected_verts:
        seen = set()
        for loop in v.link_loops:
            uv = loop[uv_layer].uv
            key = (round(uv.x, 4), round(uv.y, 4))
            if key in seen:
                continue
            seen.add(key)
            screen_pos = view2d.view_to_region(uv.x, uv.y, clip=False)
            if screen_pos:
                blf.position(font_id, screen_pos[0] + 3, screen_pos[1] + 3, 0)
                blf.draw(font_id, str(v.index))

def draw_loop_ids_uv(context, obj):
    bm = bmesh.from_edit_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        return
    
    font_id = 0
    blf.size(font_id, 18)
    blf.color(font_id, 1.0, 0.6, 0.2, 1.0)
    
    region = context.region
    view2d = region.view2d
    
    selected_verts = [v for v in bm.verts if v.select]
    
    uv_to_loops = {}
    for v in selected_verts:
        for loop in v.link_loops:
            uv = loop[uv_layer].uv
            key = (round(uv.x, 4), round(uv.y, 4))
            uv_to_loops.setdefault(key, []).append(loop.index)
    
    for (uv_x, uv_y), loop_indices in uv_to_loops.items():
        screen_pos = view2d.view_to_region(uv_x, uv_y, clip=False)
        if screen_pos:
            text = ",".join(map(str, loop_indices))
            blf.position(font_id, screen_pos[0] + 3, screen_pos[1] - 16, 0)
            blf.draw(font_id, text)

def draw_callback_uv():
    draw_uv_overlay(bpy.context)

def draw_callback_px():
    draw_shape_key_overlay(bpy.context)

class O_CopySelectedVertexIds(bpy.types.Operator):
    bl_idname = "xqfa.copy_selected_vertex_ids"
    bl_label = "复制选中顶点ID"
    bl_description = "复制选中顶点的ID到剪贴板，支持多种格式"
    
    format: bpy.props.EnumProperty(
        name="格式",
        items=[
            ('COMMA', "逗号分隔", ""),
            ('NEWLINE', "换行分隔", ""),
            ('SPACE', "空格分隔", ""),
            ('LIST', "Python列表", ""),
        ],
        default='COMMA'
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "请选择一个网格物体")
            return {'CANCELLED'}
        
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            selected_ids = [v.index for v in bm.verts if v.select]
        else:
            selected_ids = [v.index for v in obj.data.vertices if v.select]
        
        if not selected_ids:
            self.report({'WARNING'}, "没有选中任何顶点")
            return {'CANCELLED'}
        
        if self.format == 'COMMA':
            text = ', '.join(map(str, selected_ids))
        elif self.format == 'NEWLINE':
            text = '\n'.join(map(str, selected_ids))
        elif self.format == 'SPACE':
            text = ' '.join(map(str, selected_ids))
        elif self.format == 'LIST':
            text = str(selected_ids)
        
        context.window_manager.clipboard = text
        self.report({'INFO'}, f"已复制 {len(selected_ids)} 个顶点ID")
        return {'FINISHED'}


class DATA_PT_ExtraObjectInfoPanel(bpy.types.Panel):
    bl_label = "额外物体信息"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        # 兼容原有逻辑：只有特定子面板激活时显示
        return (getattr(context.scene, 'active_xbone_subpanel', '') == 'AttributeTools' and context.object is not None)

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(context.scene, "show_extra_object_info", text="显示左下角信息", icon="INFO")
        col.prop(context.scene, "show_vertex_ids", text="显示顶点ID", icon="RESTRICT_SELECT_OFF")
        col.prop(context.scene, "show_loop_ids", text="显示面拐ID", icon="LOOP_FORWARDS")

        col.separator()
        col.label(text="UV 编辑器:", icon="UV")
        col.prop(context.scene, "show_vertex_ids_uv", text="显示顶点ID", icon="RESTRICT_SELECT_OFF")
        col.prop(context.scene, "show_loop_ids_uv", text="显示面拐ID", icon="LOOP_FORWARDS")

        col.separator()
        col.operator(O_CopySelectedVertexIds.bl_idname, text="复制顶点ID", icon="COPYDOWN")

def register():
    bpy.utils.register_class(DATA_PT_ExtraObjectInfoPanel)
    bpy.utils.register_class(O_CopySelectedVertexIds)
    
    bpy.types.Scene.show_extra_object_info = bpy.props.BoolProperty(name="物体额外信息", default=True)
    bpy.types.Scene.show_vertex_ids = bpy.props.BoolProperty(name="显示选中顶点ID", default=False)
    bpy.types.Scene.show_loop_ids = bpy.props.BoolProperty(name="显示面拐ID", default=False)
    bpy.types.Scene.show_vertex_ids_uv = bpy.props.BoolProperty(name="UV显示顶点ID", default=False)
    bpy.types.Scene.show_loop_ids_uv = bpy.props.BoolProperty(name="UV显示面拐ID", default=False)
    
    global _draw_handle
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_px, (), 'WINDOW', 'POST_PIXEL'
        )
    
    global _draw_handle_uv
    if _draw_handle_uv is None:
        _draw_handle_uv = bpy.types.SpaceImageEditor.draw_handler_add(
            draw_callback_uv, (), 'WINDOW', 'POST_PIXEL'
        )

def unregister():
    bpy.utils.unregister_class(DATA_PT_ExtraObjectInfoPanel)
    bpy.utils.unregister_class(O_CopySelectedVertexIds)
    
    del bpy.types.Scene.show_extra_object_info
    del bpy.types.Scene.show_vertex_ids
    del bpy.types.Scene.show_loop_ids
    del bpy.types.Scene.show_vertex_ids_uv
    del bpy.types.Scene.show_loop_ids_uv
    
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
    
    global _draw_handle_uv
    if _draw_handle_uv is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_draw_handle_uv, 'WINDOW')
        _draw_handle_uv = None

if __name__ == "__main__":
    register()