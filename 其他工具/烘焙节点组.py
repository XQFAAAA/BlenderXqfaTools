# type: ignore
import bpy
import os

# --- 1. 存储输出端口的属性组 ---
class MultiOutputItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    selected: bpy.props.BoolProperty(default=False)

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
                found_groups.append((node.name, label, f"来自节点组: {node.node_tree.name}"))
        return found_groups if found_groups else items

    def update_outputs(self, context):
        obj = context.active_object
        if not obj or not obj.active_material: return
        mat = obj.active_material
        self.output_items.clear()
        target_node = mat.node_tree.nodes.get(self.target_group)
        if target_node and target_node.type == 'GROUP':
            for output in target_node.outputs:
                item = self.output_items.add()
                item.name = output.name
                item.selected = False
    
    def validate_resolution(self, context):
        # 确保分辨率是正整数
        try:
            res = int(self.bake_resolution)
            if res <= 0:
                self.bake_resolution = "2048"
        except ValueError:
            self.bake_resolution = "2048"

    target_group: bpy.props.EnumProperty(name="节点组", items=get_group_items, update=update_outputs)
    output_items: bpy.props.CollectionProperty(type=MultiOutputItem)
    # 改为字符串属性，允许自定义输入
    bake_resolution: bpy.props.StringProperty(
        name="分辨率",
        default="2048",
        description="输入分辨率，例如：1024, 2048, 4096",
        update=validate_resolution
    )
    export_path: bpy.props.StringProperty(name="保存路径", default="//", subtype='DIR_PATH')

# --- 快速设置分辨率的操作算子 ---
class M_OT_SetBakeResolution(bpy.types.Operator):
    bl_idname = "scene.set_bake_resolution"
    bl_label = "设置烘焙分辨率"
    bl_description = "快速设置烘焙分辨率"
    
    resolution: bpy.props.StringProperty()
    
    def execute(self, context):
        props = context.scene.batch_bake_props
        props.bake_resolution = self.resolution
        return {'FINISHED'}

# --- 3. 模态烘焙操作算子 ---
class M_OT_BatchBakeModal(bpy.types.Operator):
    bl_idname = "object.batch_bake_modal"
    bl_label = "批量烘焙 (动态)"
    
    _timer = None
    _queue = []
    _original_source = None
    _export_dir = ""
    _is_baking = False

    def modal(self, context, event):
        # 允许用户通过 ESC 键中断
        if event.type == 'ESC':
            return self.cancel(context)

        if event.type == 'TIMER':
            # 如果队列为空且当前没在烘焙，说明全部完成
            if not self._queue and not self._is_baking:
                return self.finish(context)

            # 如果当前没有在烘焙，从队列取出一个开始
            if not self._is_baking and self._queue:
                self.run_next_bake(context)

        return {'PASS_THROUGH'}

    def run_next_bake(self, context):
        self._is_baking = True
        item_name = self._queue.pop(0)
        props = context.scene.batch_bake_props
        obj = context.active_object
        mat = obj.active_material
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        group_node = nodes.get(props.target_group)
        output_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
        surface_input = output_node.inputs['Surface']

        try:
            # 1. 连接
            source_socket = group_node.outputs.get(item_name)
            links.new(source_socket, surface_input)

            # 2. 图像准备
            # 转换分辨率，确保是整数
            try:
                res = int(props.bake_resolution)
                if res <= 0:
                    res = 2048
            except ValueError:
                res = 2048
                
            img_name = f"Bake_{group_node.node_tree.name}_{item_name}"
            image = bpy.data.images.get(img_name) or bpy.data.images.new(img_name, width=res, height=res)
            image.scale(res, res)

            # 3. 临时节点
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = image
            nodes.active = tex_node

            # 4. 执行烘焙 (此步仍会短暂阻塞，但每个图之间会释放 UI)
            bpy.ops.object.bake(type='EMIT')

            # 5. 保存
            file_path = os.path.join(self._export_dir, f"{img_name}.png")
            image.file_format = 'PNG'
            image.save_render(file_path)
            
            # 6. 清理
            nodes.remove(tex_node)
            self.report({'INFO'}, f"完成: {item_name}")

        except Exception as e:
            self.report({'ERROR'}, f"出错: {str(e)}")
        
        self._is_baking = False

    def execute(self, context):
        props = context.scene.batch_bake_props
        obj = context.active_object
        
        # 初始化检查
        if not obj or not obj.active_material:
            self.report({'ERROR'}, "未选中物体或材质")
            return {'CANCELLED'}

        # 路径准备
        self._export_dir = bpy.path.abspath(props.export_path)
        if not os.path.exists(self._export_dir):
            os.makedirs(self._export_dir)

        # 记录原始连接
        mat = obj.active_material
        output_node = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if output_node and output_node.inputs['Surface'].is_linked:
            self._original_source = output_node.inputs['Surface'].links[0].from_socket

        # 填充队列
        self._queue = [item.name for item in props.output_items if item.selected]
        if not self._queue:
            self.report({'WARNING'}, "未选择任何端口")
            return {'CANCELLED'}

        # 启动计时器
        self._is_baking = False
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        
        self.report({'INFO'}, "开始批量烘焙 (按 ESC 取消)")
        return {'RUNNING_MODAL'}

    def finish(self, context):
        self.restore_connection(context)
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self.report({'INFO'}, "批量烘焙全部完成！")
        return {'FINISHED'}

    def cancel(self, context):
        self.restore_connection(context)
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self.report({'WARNING'}, "烘焙已取消")
        return {'CANCELLED'}

    def restore_connection(self, context):
        obj = context.active_object
        output_node = next((n for n in obj.active_material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if output_node:
            surface_input = output_node.inputs['Surface']
            if self._original_source:
                obj.active_material.node_tree.links.new(self._original_source, surface_input)
            elif surface_input.is_linked:
                obj.active_material.node_tree.links.remove(surface_input.links[0])

# --- 4. UI 面板 ---
class M_PT_BatchBakePanel(bpy.types.Panel):
    bl_label = "烘焙节点组"
    bl_idname = "M_PT_batch_bake_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Bake"

    def draw(self, context):
        layout = self.layout
        props = context.scene.batch_bake_props
        
        box = layout.box()
        box.label(text="1. 选择节点组:", icon='NODETREE')
        box.prop(props, "target_group", text="")
        
        box = layout.box()
        box.label(text="2. 选择要烘焙的组输出:", icon='OUTPUT')
        col = box.column(align=True)
        for item in props.output_items:
            col.prop(item, "selected", text=item.name)
            
        box = layout.box()
        box.label(text="3. 纹理设置:", icon='IMAGE_RGB_ALPHA')
        
        # 分辨率设置行，左侧为输入框，右侧为按钮组
        row = box.row(align=True)
        row.label(text="分辨率:")
        row.prop(props, "bake_resolution", text="")
        
        # 快速设置按钮
        row.operator("scene.set_bake_resolution", text="1k").resolution = "1024"
        row.operator("scene.set_bake_resolution", text="2k").resolution = "2048"
        row.operator("scene.set_bake_resolution", text="4k").resolution = "4096"
        
        box.prop(props, "export_path", text="保存路径")
        
        layout.separator()
        # 调用新的模态算子
        layout.operator("object.batch_bake_modal", icon='RENDER_STILL', text="开始烘焙")

# --- 注册 ---
def register():
    bpy.utils.register_class(MultiOutputItem)
    bpy.utils.register_class(BatchBakeProperties)
    bpy.utils.register_class(M_OT_SetBakeResolution)
    bpy.utils.register_class(M_OT_BatchBakeModal)
    bpy.utils.register_class(M_PT_BatchBakePanel)
    bpy.types.Scene.batch_bake_props = bpy.props.PointerProperty(type=BatchBakeProperties)

def unregister():
    del bpy.types.Scene.batch_bake_props
    bpy.utils.unregister_class(M_PT_BatchBakePanel)
    bpy.utils.unregister_class(M_OT_BatchBakeModal)
    bpy.utils.unregister_class(M_OT_SetBakeResolution)
    bpy.utils.unregister_class(BatchBakeProperties)
    bpy.utils.unregister_class(MultiOutputItem)

if __name__ == "__main__":
    register()