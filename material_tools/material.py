# type: ignore
import bpy
from bpy.props import IntProperty
import numpy as np

class XQFA_OT_detect_normal_format(bpy.types.Operator):
    """基于 Sobel 算子和全图向量化运算的法线格式诊断"""
    bl_idname = "xqfa.detect_normal_format"
    bl_label = "深度法线分析 (Sobel)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        node = context.active_node
        if not node or node.type != 'TEX_IMAGE' or not node.image:
            self.report({'ERROR'}, "请选择一个法线贴图节点")
            return {'CANCELLED'}

        img = node.image
        w, h = img.size
        
        # 1. 快速读取并重构数据
        pixels = np.empty(w * h * img.channels, dtype=np.float32)
        img.pixels.foreach_get(pixels)
        # 仅提取 R(0) 和 G(1) 通道，重映射到 [-1, 1]
        img_data = pixels.reshape((h, w, img.channels))
        R = img_data[:, :, 0] * 2.0 - 1.0
        G = img_data[:, :, 1] * 2.0 - 1.0

        # 2. 定义 Sobel 算子进行梯度提取
        # dx_kernel 捕捉水平边缘，dy_kernel 捕捉垂直边缘
        def sobel_v(a):
            """向量化 Sobel 计算"""
            # 计算 R 通道在 X 方向的梯度 (Horizontal)
            # 结果 (H-2, W-2)
            dx = (a[0:-2, 2:] + 2*a[1:-1, 2:] + a[2:, 2:]) - \
                 (a[0:-2, 0:-2] + 2*a[1:-1, 0:-2] + a[2:, 0:-2])
            # 计算 G 通道在 Y 方向的梯度 (Vertical)
            dy = (a[2:, 0:-2] + 2*a[2:, 1:-1] + a[2:, 2:]) - \
                 (a[0:-2, 0:-2] + 2*a[0:-2, 1:-1] + a[0:-2, 2:])
            return dx, dy

        # 3. 执行核心分析
        # 我们关注 R 通道的 X 变化与 G 通道的 Y 变化之间的相关性
        dR_dx, _ = sobel_v(R)
        _, dG_dy = sobel_v(G)

        # 核心逻辑：在 OpenGL 中，R+ 对应向右，G+ 对应向上。
        # 当表面凸起时，dR/dx 与 dG/dy 的乘积在特定光照模型下具有统计学特征。
        # 这里的判定逻辑基于切线空间坐标系的数学一致性。
        score_map = dR_dx * dG_dy
        
        # 过滤掉变化极小的平坦区域 (阈值控制)
        threshold = 0.01
        valid_mask = np.abs(score_map) > threshold
        valid_scores = score_map[valid_mask]

        if valid_scores.size == 0:
            self.report({'WARNING'}, "分析失败：贴图过于平滑，无法提取特征")
            return {'FINISHED'}

        # 4. 判定结果
        final_score = np.sum(valid_scores)
        
        # 根据统计概率，OpenGL 格式在 Blender 采样下通常呈现正相关性
        if final_score > 0:
            res_str = "OpenGL (Y+)"
            confidence = (np.sum(valid_scores > 0) / valid_scores.size) * 100
        else:
            res_str = "DirectX (Y-)"
            confidence = (np.sum(valid_scores < 0) / valid_scores.size) * 100

        # 5. 输出报告
        msg = f"判定结果: {res_str} | 置信度: {confidence:.1f}% | 有效像素占比: {(valid_scores.size / score_map.size)*100:.1f}%"
        self.report({'INFO'}, msg)
        
        print(f"--- Sobel 法线分析报告 ---")
        print(f"Score Sum: {final_score:.4f}")
        print(f"Valid Pixels: {valid_scores.size}")
        print(f"Format: {res_str}")
        
        return {'FINISHED'}

class XQFA_OT_add_packed_image(bpy.types.Operator):
    """创建已打包图像"""
    bl_idname = "xqfa.add_packed_image"
    bl_label = "创建已打包图像"
    bl_options = {'REGISTER', 'UNDO'}

    width: IntProperty(name="宽度", default=2048, min=1, max=16384)
    height: IntProperty(name="高度", default=2048, min=1, max=16384)

    def execute(self, context):
        if not context.active_object or not context.active_object.active_material:
            self.report({'ERROR'}, "请先选择带有材质的对象")
            return {'CANCELLED'}
        
        mat = context.active_object.active_material
        nodes = mat.node_tree.nodes
        image_name = "已打包图像"
            
        image = bpy.data.images.new(
            name=image_name, width=self.width, height=self.height,
            alpha=True, float_buffer=False, is_data=False, tiled=False
        )
        
        mouse_x = context.space_data.cursor_location[0]
        mouse_y = context.space_data.cursor_location[1]
        
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = image
        tex_node.location = (mouse_x, mouse_y)
        
        pixels = list(image.pixels)
        pixels[0:4] = [1.0, 1.0, 1.0, 1.0]
        image.pixels = pixels
        image.update()
        image.pack()
        
        self.report({'INFO'}, f"已创建打包图像纹理 {self.width}x{self.height}")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        context.space_data.cursor_location_from_region(event.mouse_region_x, event.mouse_region_y)
        return context.window_manager.invoke_props_dialog(self)


class XQFA_OT_add_material(bpy.types.Operator):
    bl_idname = "xqfa.add_material"
    bl_label = "新建3贴图材质"
    bl_options = {'REGISTER', 'UNDO'}

    width: IntProperty(name="宽度", default=2048, min=1, max=16384)
    height: IntProperty(name="高度", default=2048, min=1, max=16384)

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "请先选择对象")
            return {'CANCELLED'}
        
        mat = obj.active_material
        if not mat:
            mat = bpy.data.materials.new(name=obj.name)
            obj.data.materials.append(mat)
        
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        bsdf = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf:
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
        
        # 基础色
        base_img = bpy.data.images.new(f"{obj.name}_BaseColor", self.width, self.height)
        self.set_default_pixels(base_img, (0.8, 0.8, 0.8, 1.0))
        base_node = self.create_image_node(nodes, base_img, (bsdf.location.x - 400, bsdf.location.y + 300))
        links.new(base_node.outputs['Color'], bsdf.inputs['Base Color'])
        
        # 金属度 (Non-Color)
        metal_img = bpy.data.images.new(f"{obj.name}_Metallic", self.width, self.height)
        metal_img.colorspace_settings.name = 'Non-Color'
        self.set_default_pixels(metal_img, (0.0, 0.0, 0.0, 1.0))
        metal_node = self.create_image_node(nodes, metal_img, (bsdf.location.x - 400, bsdf.location.y))
        links.new(metal_node.outputs['Color'], bsdf.inputs['Metallic'])
        
        # 粗糙度 (Non-Color)
        rough_img = bpy.data.images.new(f"{obj.name}_Roughness", self.width, self.height)
        rough_img.colorspace_settings.name = 'Non-Color'
        self.set_default_pixels(rough_img, (0.5, 0.5, 0.5, 1.0))
        rough_node = self.create_image_node(nodes, rough_img, (bsdf.location.x - 400, bsdf.location.y - 300))
        links.new(rough_node.outputs['Color'], bsdf.inputs['Roughness'])
        
        return {'FINISHED'}

    def set_default_pixels(self, image, color):
        image.pixels = list(color) * (image.size[0] * image.size[1])
        image.update()
        image.pack()
    
    def create_image_node(self, nodes, image, location):
        node = nodes.new('ShaderNodeTexImage')
        node.image = image
        node.location = location
        return node

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class XQFA_OT_ensure_material(bpy.types.Operator):
    """为所有选中的无材质物体创建同名材质"""
    bl_idname = "xqfa.ensure_material"
    bl_label = "批量创建材质"
    bl_description = "遍历选中物体：如果物体没有材质，则创建一个以物体名命名的材质"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None

    def execute(self, context):
        created_count = 0
        assigned_count = 0
        
        for obj in context.selected_objects:
            # 只处理网格或可以拥有材质的物体类型
            if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}:
                continue
                
            # 检查物体是否有材质槽且槽位中是否有材质
            has_material = False
            if obj.material_slots:
                for slot in obj.material_slots:
                    if slot.material:
                        has_material = True
                        break
            
            if not has_material:
                # 检查 Blender 数据中是否已经存在同名材质
                mat_name = obj.name
                mat = bpy.data.materials.get(mat_name)
                
                if mat is None:
                    # 创建新材质
                    mat = bpy.data.materials.new(name=mat_name)
                    mat.use_nodes = True  # 默认开启节点以便后续编辑
                    created_count += 1
                
                # 分配材质
                if not obj.data.materials:
                    obj.data.materials.append(mat)
                else:
                    obj.data.materials[0] = mat
                assigned_count += 1

        self.report({'INFO'}, f"材质补全完成：新建 {created_count} 个，分配给 {assigned_count} 个物体")
        return {'FINISHED'}


class XQFA_PT_material_tools(bpy.types.Panel):
    """在节点编辑器侧边栏中添加面板"""
    bl_label = "XQFA 材质工具"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "XQFA"
    
    def draw(self, context):
        layout = self.layout
        
        col = layout.column()
        col.operator(XQFA_OT_add_packed_image.bl_idname, icon='IMAGE_DATA')
        col.operator(XQFA_OT_add_material.bl_idname, icon='MATERIAL')
        col.operator(XQFA_OT_detect_normal_format.bl_idname, icon='NODE_SEL')
        col.operator(XQFA_OT_ensure_material.bl_idname, icon='MATERIAL_DATA')

classes = (
    XQFA_OT_detect_normal_format,
    XQFA_OT_add_packed_image,
    XQFA_OT_add_material,
    XQFA_OT_ensure_material,
    XQFA_PT_material_tools,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

