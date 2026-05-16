# type: ignore
import bpy
import blf

# 绘制处理器
_draw_handle = None

def draw_shape_key_overlay(context):
    # 检查是否启用物体额外信息
    if not hasattr(context.scene, "show_extra_object_info") or \
       not context.scene.show_extra_object_info:
        return
    
    obj = context.active_object
    
    # 获取顶点组信息
    vertex_group_count = 0
    current_vertex_group = "无"
    if obj and obj.vertex_groups:
        vertex_group_count = len(obj.vertex_groups)
        # 直接尝试获取激活的顶点组
        try:
            # 在Blender中，通常active_vertex_group就在vertex_groups上
            if vertex_group_count > 0:
                # 尝试几种方式获取
                if hasattr(obj.vertex_groups, 'active'):
                    current_vertex_group = obj.vertex_groups.active.name
                elif hasattr(obj, 'active_vertex_group_index'):
                    idx = obj.active_vertex_group_index
                    if idx >= 0 and idx < vertex_group_count:
                        current_vertex_group = obj.vertex_groups[idx].name
                elif hasattr(obj.vertex_groups, 'active_index'):
                    idx = obj.vertex_groups.active_index
                    if idx >= 0 and idx < vertex_group_count:
                        current_vertex_group = obj.vertex_groups[idx].name
        except:
            current_vertex_group = "无"
    vg_text = f"顶点组: {current_vertex_group} / {vertex_group_count}"
    
    # 获取形态键信息
    shape_key_count = 0
    current_shape_key = ""
    if obj and obj.type == 'MESH' and obj.data.shape_keys:
        shape_keys = obj.data.shape_keys
        shape_key_count = len(shape_keys.key_blocks)
        active_index = obj.active_shape_key_index
        if active_index >= 0 and active_index < shape_key_count:
            current_shape_key = shape_keys.key_blocks[active_index].name
        else:
            current_shape_key = "无"
    else:
        current_shape_key = "无"
    sk_text = f"形态键: {current_shape_key} / {shape_key_count}"
    
    # 绘制文本 - 位置在左下角
    font_id = 0
    blf.size(font_id, 12)
    
    # 计算位置
    region = context.region
    if region:
        # 绘制形态键（在上面）
        sk_text_width, sk_text_height = blf.dimensions(font_id, sk_text)
        sk_x_pos = 10
        sk_y_pos = 30
        blf.position(font_id, sk_x_pos, sk_y_pos, 0)
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
        blf.draw(font_id, sk_text)
        
        # 绘制顶点组（在下面）
        vg_text_width, vg_text_height = blf.dimensions(font_id, vg_text)
        vg_x_pos = 10
        vg_y_pos = 50
        blf.position(font_id, vg_x_pos, vg_y_pos, 0)
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
        blf.draw(font_id, vg_text)

def draw_callback_px():
    draw_shape_key_overlay(bpy.context)

def register():
    # 添加自定义属性到Scene
    bpy.types.Scene.show_extra_object_info = bpy.props.BoolProperty(
        name="物体额外信息",
        description="显示顶点组和形态键数量信息",
        default=False
    )
    
    # 添加绘制处理器
    global _draw_handle
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_px, (), 'WINDOW', 'POST_PIXEL'
        )

def unregister():
    # 移除自定义属性
    if hasattr(bpy.types.Scene, "show_extra_object_info"):
        del bpy.types.Scene.show_extra_object_info
    
    # 移除绘制处理器
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None

if __name__ == "__main__":
    register()
