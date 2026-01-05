# type: ignore
import bpy
import os
import numpy as np

# --- 1. 存储输出端口的属性组 ---
class MultiOutputItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    selected: bpy.props.BoolProperty(default=False)
    is_normal: bpy.props.BoolProperty(name="法线", default=False)
    is_bw: bpy.props.BoolProperty(name="灰度", default=False)
    is_linear: bpy.props.BoolProperty(name="线性", default=True)

# --- 新增：通道选择项 ---
class ChannelConfig(bpy.types.PropertyGroup):
    # 引用来源输出节点的名称
    source_output: bpy.props.StringProperty(name="来源输出", default="")
    # 选择来源的具体通道：R, G, B, A, 或 Mean(BW)
    channel_src: bpy.props.EnumProperty(
        name="分量",
        items=[
            ('R', 'R', ""),
            ('G', 'G', ""),
            ('B', 'B', ""),
            ('A', 'A', ""),
            ('L', 'L', "")
        ],
        default='L'
    )

class PackImageItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="图片名", default="Pack_Result")
    # 为 RGBA 四个通道分别创建配置
    r: bpy.props.PointerProperty(type=ChannelConfig)
    g: bpy.props.PointerProperty(type=ChannelConfig)
    b: bpy.props.PointerProperty(type=ChannelConfig)
    a: bpy.props.PointerProperty(type=ChannelConfig)

# --- 2. 核心属性管理 ---
class BatchBakeProperties(bpy.types.PropertyGroup):
    def get_group_items(self, context):
        items = [("NONE", "请选择节点组...", "0")]
        obj = context.active_object
        if not obj or not obj.active_material or not obj.active_material.use_nodes:
            return items
        nodes = obj.active_material.node_tree.nodes
        found_groups = []
        for node in nodes:
            if node.type == 'GROUP' and node.node_tree:
                label = f"{node.node_tree.name} ({node.name})"
                found_groups.append((node.node_tree.name, label, ""))
        return found_groups if found_groups else items

    def update_outputs(self, context):
        obj = context.active_object
        if not obj or not obj.active_material: return
        mat = obj.active_material
        self.output_items.clear()
        target_node = next((n for n in mat.node_tree.nodes if n.type == 'GROUP' and n.node_tree.name == self.target_group), None)
        if target_node:
            for output in target_node.outputs:
                item = self.output_items.add()
                item.name = output.name
                tp = output.type
                if tp == 'SHADER':
                    item.is_normal, item.is_bw, item.is_linear = True, False, False
                elif tp in {'VALUE', 'INT', 'BOOLEAN'}:
                    item.is_normal, item.is_bw, item.is_linear = False, True, True
                elif tp == 'VECTOR':
                    item.is_normal, item.is_bw, item.is_linear = False, False, True
                else:
                    item.is_normal, item.is_bw, item.is_linear = False, False, False

    target_group: bpy.props.EnumProperty(name="节点组", items=get_group_items, update=update_outputs)
    output_items: bpy.props.CollectionProperty(type=MultiOutputItem)
    
    # 打包相关属性
    pack_items: bpy.props.CollectionProperty(type=PackImageItem)
    pack_index: bpy.props.IntProperty()
    
    bake_resolution: bpy.props.StringProperty(name="分辨率", default="2048")
    file_prefix: bpy.props.StringProperty(name="名称前缀", default="Bake")
    export_path: bpy.props.StringProperty(name="保存路径", default="//", subtype='DIR_PATH')

    # 控制 UI 折叠状态
    show_outputs: bpy.props.BoolProperty(name="展开输出端口", default=True)
    show_packing: bpy.props.BoolProperty(name="展开通道打包", default=True)
    show_settings: bpy.props.BoolProperty(name="展开导出设置", default=True)

# --- 3. 核心烘焙逻辑 ---
class M_OT_BatchBakeModal(bpy.types.Operator):
    bl_idname = "object.batch_bake_modal"
    bl_label = "批量烘焙 (打包增强版)"
    
    _timer = None
    _queue = []
    _export_dir = ""
    _is_baking = False
    _original_links = {}
    _baked_images = {} # 用于存储本次烘焙生成的图像对象引用

    def modal(self, context, event):
        if event.type == 'ESC': return self.cancel(context)
        if event.type == 'TIMER':
            if not self._queue and not self._is_baking: return self.finish(context)
            if not self._is_baking and self._queue: self.run_next_bake(context)
        return {'PASS_THROUGH'}

    def run_next_bake(self, context):
        self._is_baking = True
        item_name, is_bw, is_linear, is_normal = self._queue.pop(0)
        props = context.scene.batch_bake_props
        
        b_type = 'NORMAL' if is_normal else 'EMIT'
        c_mode = 'BW' if is_bw else 'RGB'
        c_space = 'Linear' if is_linear else 'sRGB'
        res = int(props.bake_resolution)
        prefix = props.file_prefix.strip()
        base_name = f"{prefix}_{props.target_group}_{item_name}"
            
        image = bpy.data.images.get(base_name) or bpy.data.images.new(base_name, width=res, height=res)
        image.scale(res, res)
        image.colorspace_settings.name = 'sRGB' if c_space == 'sRGB' else 'Non-Color'
        self._baked_images[item_name] = image # 记录以便后续打包

        temp_nodes = [] 
        selected_objs = [o for o in context.selected_objects if o.type == 'MESH']
        
        for obj in selected_objs:
            for slot in obj.material_slots:
                mat = slot.material
                if not mat or not mat.use_nodes: continue
                nodes = mat.node_tree.nodes
                group_node = next((n for n in nodes if n.type == 'GROUP' and n.node_tree.name == props.target_group), None)
                output_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
                if not group_node or not output_node: continue
                source_socket = group_node.outputs.get(item_name)
                if not source_socket: continue

                if b_type == 'EMIT' or source_socket.type == 'SHADER':
                    mat.node_tree.links.new(source_socket, output_node.inputs['Surface'])
                else:
                    n_map = nodes.new('ShaderNodeNormalMap')
                    d_bsdf = nodes.new('ShaderNodeBsdfDiffuse')
                    temp_nodes.extend([(mat, n_map), (mat, d_bsdf)])
                    mat.node_tree.links.new(source_socket, n_map.inputs['Color'])
                    mat.node_tree.links.new(n_map.outputs['Normal'], d_bsdf.inputs['Normal'])
                    mat.node_tree.links.new(d_bsdf.outputs['BSDF'], output_node.inputs['Surface'])

                tex_node = nodes.new('ShaderNodeTexImage')
                tex_node.image = image
                nodes.active = tex_node
                temp_nodes.append((mat, tex_node))

        try:
            bpy.ops.object.bake(type=b_type)
            file_path = os.path.join(self._export_dir, f"{base_name}.png")
            image.file_format = 'PNG'
            old_mode = context.scene.render.image_settings.color_mode
            context.scene.render.image_settings.color_mode = c_mode
            image.save_render(file_path, scene=context.scene)
            context.scene.render.image_settings.color_mode = old_mode
        except Exception as e:
            self.report({'ERROR'}, f"烘焙失败: {str(e)}")
        
        for mat, node in temp_nodes:
            mat.node_tree.nodes.remove(node)
        self._is_baking = False

    def execute(self, context):
        props = context.scene.batch_bake_props
        selected_objs = [o for o in context.selected_objects if o.type == 'MESH']
        if not selected_objs: return {'CANCELLED'}
        
        self._export_dir = bpy.path.abspath(props.export_path)
        if not os.path.exists(self._export_dir): os.makedirs(self._export_dir)
        
        self._baked_images.clear()
        self._original_links.clear()
        # 记录原始连接... (省略部分同原代码)
        for obj in selected_objs:
            for slot in obj.material_slots:
                mat = slot.material
                if mat and mat.use_nodes:
                    out = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
                    if out and out.inputs['Surface'].is_linked:
                        self._original_links[mat.name] = out.inputs['Surface'].links[0].from_socket

        self._queue = [(i.name, i.is_bw, i.is_linear, i.is_normal) for i in props.output_items if i.selected]
        if not self._queue: return {'CANCELLED'}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def process_packing(self, context):
        """核心打包逻辑：确保导出为 TGA"""
        props = context.scene.batch_bake_props
        res = int(props.bake_resolution)
        
        # 记录原始渲染设置，以便保存后恢复
        render_settings = context.scene.render.image_settings
        old_format = render_settings.file_format
        old_color_mode = render_settings.color_mode
        old_depth = render_settings.color_depth

        # 设置为 TGA RGBA 模式
        render_settings.file_format = 'TARGA'
        render_settings.color_mode = 'RGBA'
        render_settings.color_depth = '8' # TGA 通常为 8bit

        for pack_cfg in props.pack_items:
            pack_img_name = f"{props.file_prefix}_{pack_cfg.name}"
            # 检查是否已存在同名图像，存在则删除以防数据残留
            if pack_img_name in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[pack_img_name])
            
            pack_img = bpy.data.images.new(pack_img_name, width=res, height=res, alpha=True)
            
            # 初始化像素阵列 (R,G,B,A) -> 默认全白 1.0
            pixels = np.ones(res * res * 4, dtype=np.float32)
            
            # 依次处理 R, G, B, A 四个通道
            for i, channel_key in enumerate(['r', 'g', 'b', 'a']):
                cfg = getattr(pack_cfg, channel_key)
                src_img = self._baked_images.get(cfg.source_output)
                
                if src_img:
                    src_pixels = np.array(src_img.pixels)
                    if len(src_pixels) == len(pixels):
                        # 提取对应通道
                        if cfg.channel_src == 'R':
                            pixels[i::4] = src_pixels[0::4]
                        elif cfg.channel_src == 'G':
                            pixels[i::4] = src_pixels[1::4]
                        elif cfg.channel_src == 'B':
                            pixels[i::4] = src_pixels[2::4]
                        elif cfg.channel_src == 'A':
                            pixels[i::4] = src_pixels[3::4]
                        elif cfg.channel_src == 'L':
                            pixels[i::4] = (src_pixels[0::4] + src_pixels[1::4] + src_pixels[2::4]) / 3.0
            
            pack_img.pixels = pixels.tolist()
            
            # 确保路径后缀正确
            save_filename = f"{pack_img_name}.tga"
            file_path = os.path.join(self._export_dir, save_filename)
            
            # 执行保存
            try:
                pack_img.save_render(file_path, scene=context.scene)
                self.report({'INFO'}, f"成功导出打包贴图: {save_filename}")
            except Exception as e:
                self.report({'ERROR'}, f"导出 TGA 失败: {str(e)}")
            
            # 清理内存中的预览图（可选，如果不需要在Blender内查看）
            # bpy.data.images.remove(pack_img)

        # 恢复原始渲染设置
        render_settings.file_format = old_format
        render_settings.color_mode = old_color_mode
        render_settings.color_depth = old_depth

    def finish(self, context):
        self.process_packing(context)
        self.restore_all_connections(context)
        context.window_manager.event_timer_remove(self._timer)
        self.report({'INFO'}, "批量烘焙及打包全部完成！")
        return {'FINISHED'}

    def cancel(self, context):
        self.restore_all_connections(context)
        context.window_manager.event_timer_remove(self._timer)
        return {'CANCELLED'}

    def restore_all_connections(self, context):
        for obj in context.selected_objects:
            if obj.type != 'MESH': continue
            for slot in obj.material_slots:
                mat = slot.material
                if mat and mat.name in self._original_links:
                    out = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
                    if out: mat.node_tree.links.new(self._original_links[mat.name], out.inputs['Surface'])

# --- 4. UI 辅助操作符 ---
class M_OT_PackItemManage(bpy.types.Operator):
    bl_idname = "object.pack_item_manage"
    bl_label = "管理打包任务"
    action: bpy.props.EnumProperty(items=[('ADD', "Add", ""), ('REMOVE', "Remove", "")])

    def execute(self, context):
        props = context.scene.batch_bake_props
        if self.action == 'ADD':
            item = props.pack_items.add()
            item.name = f"Pack_{len(props.pack_items)}"
        else:
            if len(props.pack_items) > 0:
                props.pack_items.remove(props.pack_index)
                props.pack_index = max(0, props.pack_index - 1)
        return {'FINISHED'}

# --- 5. UI 面板 ---
class M_UL_PackList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.label(text=item.name, icon='IMAGE_RGB_ALPHA')

class M_PT_BatchBakePanel(bpy.types.Panel):
    bl_label = "节点组烘焙"
    bl_idname = "M_PT_batch_bake_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "XQFA"

    def draw(self, context):
        layout = self.layout
        props = context.scene.batch_bake_props
        
        layout.prop(props, "target_group")

        # --- 1. 选择输出端口 (可折叠) ---
        box = layout.box()
        row = box.row(align=True)
        # 使用自定义的箭头发亮属性名，'TRIA_DOWN' 或 'TRIA_RIGHT'
        icon = 'TRIA_DOWN' if props.show_outputs else 'TRIA_RIGHT'
        row.prop(props, "show_outputs", text="选择输出", icon=icon, emboss=False)
        
        if props.show_outputs:
            col = box.column(align=True)
            for item in props.output_items:
                row = col.row(align=True)
                row.prop(item, "selected", text=item.name, toggle=True)
                row.prop(item, "is_normal", text='', icon='NORMALS_FACE', toggle=True)
                row.prop(item, "is_bw", text='', icon='IMAGE_ALPHA', toggle=True)
                row.prop(item, "is_linear", text='', icon='EVENT_L', toggle=True)

        
        # --- 2. 通道打包 (可折叠) ---
        box = layout.box()
        row = box.row(align=True)
        icon = 'TRIA_DOWN' if props.show_packing else 'TRIA_RIGHT'
        row.prop(props, "show_packing", text="通道打包", icon=icon, emboss=False)
        
        if props.show_packing:
            row = box.row()
            row.template_list("M_UL_PackList", "", props, "pack_items", props, "pack_index")
            
            col = row.column(align=True)
            col.operator("object.pack_item_manage", icon='ADD', text="").action = 'ADD'
            col.operator("object.pack_item_manage", icon='REMOVE', text="").action = 'REMOVE'

            # 选中项详情配置
            if props.pack_items and props.pack_index < len(props.pack_items):
                active_pack = props.pack_items[props.pack_index]
                col = box.column(align=False)
                col.prop(active_pack, "name", text="图片名")
                
                for ch_name in ['r', 'g', 'b', 'a']:
                    cfg = getattr(active_pack, ch_name)
                    split = col.split(factor=0.1, align=True)
                    split.label(text=ch_name.upper())
                    row = split.row(align=True)
                    row.prop_search(cfg, "source_output", props, "output_items", text="")
                    row.prop(cfg, "channel_src", text="")


        # --- 3. 导出设置 (可折叠) ---
        box = layout.box()
        row = box.row(align=True)
        icon = 'TRIA_DOWN' if props.show_settings else 'TRIA_RIGHT'
        row.prop(props, "show_settings", text="导出设置", icon=icon, emboss=False)
        
        if props.show_settings:
            col = box.column(align=False)
            col.prop(props, "bake_resolution")
            col.prop(props, "file_prefix")
            col.prop(props, "export_path")
        
        layout.operator("object.batch_bake_modal", icon='RENDER_STILL', text="开始烘焙并打包")

# --- 注册 ---
classes = (
    ChannelConfig,
    PackImageItem,
    MultiOutputItem,
    BatchBakeProperties,
    M_OT_BatchBakeModal,
    M_OT_PackItemManage,
    M_UL_PackList,
    M_PT_BatchBakePanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.batch_bake_props = bpy.props.PointerProperty(type=BatchBakeProperties)

def unregister():
    del bpy.types.Scene.batch_bake_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()