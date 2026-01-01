# type: ignore
import bpy
from bpy.props import IntProperty
import numpy as np

class NODE_OT_detect_normal_format(bpy.types.Operator):
    """通过多区域采样分析法线格式"""
    bl_idname = "xqfa.detect_normal_format"
    bl_label = "多区域采样分析"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        node = context.active_node
        if not node or node.type != 'TEX_IMAGE' or not node.image:
            self.report({'ERROR'}, "请选择一个法线贴图节点")
            return {'CANCELLED'}

        img = node.image
        width, height = img.size
        
        # 1. 快速读取像素数据
        pixels = np.empty(width * height * img.channels, dtype=np.float32)
        img.pixels.foreach_get(pixels)
        pixels = pixels.reshape((height, width, img.channels))

        # 2. 定义采样参数
        grid_size = 4        # 4x4 网格采样
        patch_size = 64      # 每个采样块的大小 (64x64像素)
        total_correlation = 0.0
        valid_patches = 0

        # 计算采样点坐标
        y_coords = np.linspace(patch_size, height - patch_size, grid_size, dtype=int)
        x_coords = np.linspace(patch_size, width - patch_size, grid_size, dtype=int)

        # 3. 循环分析每个采样区域
        for y in y_coords:
            for x in x_coords:
                # 提取采样块 (R 和 G 通道)
                patch_r = pixels[y : y + patch_size, x : x + patch_size, 0]
                patch_g = pixels[y : y + patch_size, x : x + patch_size, 1]

                # 计算梯度
                # dr_dx: (patch_size, patch_size-1) -> 裁切为 (patch_size-1, patch_size-1)
                dr_dx = np.diff(patch_r, axis=1)[:-1, :]
                # dg_dy: (patch_size-1, patch_size) -> 裁切为 (patch_size-1, patch_size-1)
                dg_dy = np.diff(patch_g, axis=0)[:, :-1]

                # 计算该区域相关性
                patch_corr = np.sum(dr_dx * dg_dy)
                
                # 过滤掉几乎没有起伏的平整区域（设置一个极小的阈值）
                if abs(patch_corr) > 0.0001:
                    total_correlation += patch_corr
                    valid_patches += 1

        # 4. 判定结果
        if valid_patches == 0:
            self.report({'WARNING'}, "所有采样区域均无明显起伏，请检查贴图是否有效")
            return {'FINISHED'}

        # 最终得分平均化
        final_score = total_correlation / valid_patches
        
        if final_score > 0:
            result = "OpenGL (Y+)"
            detail = "特征：R与G梯度正相关（颜色按顺时针分布）"
        else:
            result = "DirectX (Y-)"
            detail = "特征：R与G梯度负相关（颜色按逆时针分布）"

        self.report({'INFO'}, f"分析完成({valid_patches}采样点)：判定为 {result}")
        print(f"XQFA Debug - 采样点: {valid_patches}, 平均得分: {final_score:.8f}, 说明: {detail}")

        return {'FINISHED'}

class NODE_OT_add_packed_image(bpy.types.Operator):
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


class NODE_OT_add_material(bpy.types.Operator):
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


class NODE_PT_xqfa_tools(bpy.types.Panel):
    """在节点编辑器侧边栏中添加面板"""
    bl_label = "XQFA 材质工具"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "XQFA"
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="创建工具", icon='ADD')
        col = box.column(align=True)
        col.operator(NODE_OT_add_packed_image.bl_idname, icon='IMAGE_DATA')
        col.operator(NODE_OT_add_material.bl_idname, icon='MATERIAL')

        box = layout.box()
        box.label(text="诊断工具", icon='INFO')
        col = box.column()
        col.operator(NODE_OT_detect_normal_format.bl_idname, icon='NODE_SEL')


def register():
    bpy.utils.register_class(NODE_OT_detect_normal_format)
    bpy.utils.register_class(NODE_OT_add_packed_image)
    bpy.utils.register_class(NODE_OT_add_material)
    bpy.utils.register_class(NODE_PT_xqfa_tools)


def unregister():
    bpy.utils.unregister_class(NODE_OT_detect_normal_format)
    bpy.utils.unregister_class(NODE_OT_add_packed_image)
    bpy.utils.unregister_class(NODE_OT_add_material)
    bpy.utils.unregister_class(NODE_PT_xqfa_tools)

