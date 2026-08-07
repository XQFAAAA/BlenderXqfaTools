# type: ignore
import bpy
from bpy.props import IntProperty, StringProperty, FloatVectorProperty
import numpy as np

class XQFA_OT_detect_normal_format(bpy.types.Operator):
    """基于 Sobel 算子和全图向量化运算的法线格式诊断"""
    bl_idname = "xqfa.detect_normal_format"
    bl_label = "法线格式分析"
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


class XQFA_OT_viewer_to_material(bpy.types.Operator):
    """将合成器 Viewer Node 结果转为打包图片并添加到当前材质"""
    bl_idname = "xqfa.viewer_to_material"
    bl_label = "Viewer 转图像节点"
    bl_description = "执行合成器，将 Viewer Node 结果创建为打包图片，添加到当前活动材质编辑器中"
    bl_options = {'REGISTER', 'UNDO'}

    color_space: bpy.props.EnumProperty(
        name="色彩空间",
        items=[
            ('NON_COLOR', "Non-Color", "保持原始数据不变，适合法线/粗糙度等数据贴图"),
            ('SRGB', "sRGB", "应用 Linear→sRGB gamma 校正，适合颜色贴图"),
        ],
        default='NON_COLOR',
    )

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.active_material is not None)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'color_space', expand=True)

    def execute(self, context):
        scene = context.scene

        # 1. 检查合成器节点树（Blender 5.0+ 用 compositing_node_group，旧版用 node_tree）
        node_tree = getattr(scene, 'compositing_node_group', None) or getattr(scene, 'node_tree', None)
        if not scene.use_nodes or not node_tree:
            self.report({'ERROR'}, "场景未启用合成器节点")
            return {'CANCELLED'}
        viewer_nodes = [n for n in node_tree.nodes if n.type == 'VIEWER']
        if not viewer_nodes:
            self.report({'ERROR'}, "合成器中没有 Viewer Node")
            return {'CANCELLED'}

        # 2. 执行合成器
        bpy.ops.render.render(write_still=False)

        # 3. 获取 Viewer 结果图片
        viewer_img = bpy.data.images.get("Viewer Node")
        if not viewer_img or viewer_img.size[0] == 0:
            self.report({'ERROR'}, "Viewer Node 结果无效，请确保 Viewer 已连接输入并重新执行")
            return {'CANCELLED'}

        # 4. 创建新图片并打包
        new_name = "Viewer_Result"
        while bpy.data.images.get(new_name):
            if "." not in new_name:
                new_name = new_name + ".001"
            else:
                parts = new_name.rsplit(".", 2)
                base = ".".join(parts[:-1]) if len(parts) > 1 else parts[0]
                num = int(parts[-1]) + 1
                new_name = "{}.{:03d}".format(base, num)

        new_img = bpy.data.images.new(
            name=new_name,
            width=viewer_img.size[0],
            height=viewer_img.size[1],
            alpha=True,
        )
        if self.color_space == 'SRGB':
            # Linear → sRGB gamma 校正 (numpy 向量化)
            w, h = viewer_img.size
            pixels = np.empty(w * h * viewer_img.channels, dtype=np.float32)
            viewer_img.pixels.foreach_get(pixels)
            pixels = pixels.reshape(h, w, viewer_img.channels)
            rgb = pixels[:, :, :3]
            mask = rgb <= 0.0031308
            rgb[mask] *= 12.92
            rgb[~mask] = 1.055 * np.power(rgb[~mask], 1.0 / 2.4) - 0.055
            new_img.pixels.foreach_set(pixels.ravel())
        else:
            new_img.pixels.foreach_set(viewer_img.pixels[:])
        new_img.alpha_mode = 'CHANNEL_PACKED'
        new_img.pack()
        # 打包后再设色彩空间，避免像素数据被重新解释
        new_img.colorspace_settings.name = 'sRGB' if self.color_space == 'SRGB' else 'Non-Color'

        # 5. 添加到当前活动材质
        mat = context.active_object.active_material
        if not mat.use_nodes:
            mat.use_nodes = True
        mat_nodes = mat.node_tree.nodes
        tex_node = mat_nodes.new('ShaderNodeTexImage')
        tex_node.image = new_img
        # 将节点放置在当前材质编辑器视图的中心
        if context.region:
            region = context.region
            center_x, center_y = region.view2d.region_to_view(
                region.width / 2, region.height / 2)
            tex_node.location = (center_x, center_y)
        else:
            tex_node.location = (0, 0)
        # tex_node.label = "Viewer Result"

        cs_label = "sRGB" if self.color_space == 'SRGB' else "Non-Color"
        self.report({'INFO'}, f"已创建打包图片 '{new_img.name}' ({new_img.size[0]}x{new_img.size[1]}, {cs_label})")
        return {'FINISHED'}


class XQFA_OT_create_packed_image(bpy.types.Operator):
    """创建指定颜色的纯色图片并打包到当前材质"""
    bl_idname = "xqfa.create_packed_image"
    bl_label = "新建打包图像"
    bl_description = "创建纯色图片，打包到 .blend 并添加到当前材质的图像纹理节点"
    bl_options = {'REGISTER', 'UNDO'}

    image_name: StringProperty(
        name="图像名称",
        default="NewPacked",
        description="新建图像的名称",
    )

    width: IntProperty(
        name="宽度",
        default=1024,
        min=4,
        max=16384,
        description="图像宽度（像素）",
    )

    height: IntProperty(
        name="高度",
        default=1024,
        min=4,
        max=16384,
        description="图像高度（像素）",
    )

    default_color: FloatVectorProperty(
        name="默认颜色",
        subtype='COLOR',
        size=4,
        default=(0.5, 0.5, 0.5, 1.0),
        min=0.0,
        max=1.0,
        description="填充图像的 RGBA 默认颜色",
    )

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.active_material is not None)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, 'image_name')
        col.prop(self, 'width')
        col.prop(self, 'height')
        col.prop(self, 'default_color')

    def execute(self, context):
        # 1. 检查活动材质
        mat = context.active_object.active_material
        if not mat.use_nodes:
            mat.use_nodes = True

        # 2. 自动去重图像名称
        name = self.image_name
        if not name:
            name = "NewPacked"
        base_name = name
        idx = 1
        while bpy.data.images.get(name):
            name = f"{base_name}.{idx:03d}"
            idx += 1

        # 3. 创建图像并填充颜色
        new_img = bpy.data.images.new(
            name=name,
            width=self.width,
            height=self.height,
            alpha=True,
        )

        # 用指定颜色填充全部像素
        w, h = self.width, self.height
        pixels = np.empty(w * h * 4, dtype=np.float32)
        r, g, b, a = self.default_color
        pixels[0::4] = r
        pixels[1::4] = g
        pixels[2::4] = b
        pixels[3::4] = a
        new_img.pixels.foreach_set(pixels)

        # 4. 打包图像并设置 alpha 模式
        new_img.alpha_mode = 'CHANNEL_PACKED'
        new_img.pack()

        # 5. 延迟添加节点：等对话框关闭后 cursor_location 才会更新
        img_name = name

        def _deferred_add_node():
            for area in bpy.context.screen.areas:
                if area.type != 'NODE_EDITOR':
                    continue
                node_space = None
                node_region = None
                for space in area.spaces:
                    if space.type == 'NODE_EDITOR':
                        node_space = space
                for region in area.regions:
                    if region.type == 'WINDOW':
                        node_region = region
                if not node_space or not node_region:
                    continue

                cur_mat = bpy.context.active_object.active_material
                if not cur_mat or not cur_mat.use_nodes:
                    return None

                cur_mat_nodes = cur_mat.node_tree.nodes
                tex_node = cur_mat_nodes.new('ShaderNodeTexImage')
                tex_node.image = bpy.data.images.get(img_name)
                tex_node.location = node_space.cursor_location

                for n in cur_mat_nodes:
                    n.select = False
                tex_node.select = True
                cur_mat_nodes.active = tex_node

                with bpy.context.temp_override(
                    area=area, region=node_region, space_data=node_space
                ):
                    bpy.ops.node.translate_attach('INVOKE_DEFAULT')
                return None
            return None  # 取消注册计时器

        bpy.app.timers.register(_deferred_add_node, first_interval=0.05)

        color_hex = "#{:02x}{:02x}{:02x}".format(
            int(r * 255), int(g * 255), int(b * 255))
        self.report({'INFO'}, f"已创建打包图像 '{name}' ({w}x{h}, 颜色: {color_hex})")
        return {'FINISHED'}


class XQFA_OT_extract_id_masks(bpy.types.Operator):
    """从活动图像节点分离 ID 遮罩"""
    bl_idname = "xqfa.extract_id_masks"
    bl_label = "分离ID遮罩"
    bl_description = ("以活动图像节点为目标，统计图片中各颜色占比，\n"
                     "按占比从高到低提取数量限制内的颜色，\n"
                     "为每种颜色生成纯黑白遮罩图片并放入当前材质（位置跟随鼠标）")
    bl_options = {'REGISTER', 'UNDO'}

    max_masks: IntProperty(
        name="遮罩数量",
        default=8,
        min=1,
        max=64,
        description="按颜色占比从高到低提取的遮罩数量上限",
    )

    quantize_levels: IntProperty(
        name="颜色量化",
        default=256,
        min=2,
        max=256,
        description="每通道颜色量化级数，256 为精确匹配，调低可合并相近颜色",
    )

    sort_mode: bpy.props.EnumProperty(
        name="排序方式",
        items=[
            ("RATIO", "按占比排序", "按颜色占比从高到低提取"),
            ("COLOR", "按颜色值排序", "按颜色值从小到大提取"),
        ],
        default="RATIO",
    )

    channels: bpy.props.BoolVectorProperty(
        name="通道",
        size=4,
        default=(True, True, True, True),
        description="参与计算与匹配的颜色通道（R/G/B/A），点击可关闭",
    )

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.active_material is not None)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=260)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "sort_mode", expand=True)
        row = layout.row(align=True)
        row.label(text="通道")
        row.prop(self, "channels", index=0, text="R", toggle=True)
        row.prop(self, "channels", index=1, text="G", toggle=True)
        row.prop(self, "channels", index=2, text="B", toggle=True)
        row.prop(self, "channels", index=3, text="A", toggle=True)
        layout.prop(self, "max_masks")
        layout.prop(self, "quantize_levels")

    def execute(self, context):
        node = context.active_node
        if not node or node.type != 'TEX_IMAGE' or not node.image:
            self.report({'ERROR'}, "请先选择一个图像节点")
            return {'CANCELLED'}

        mat = context.active_object.active_material
        if not mat:
            self.report({'ERROR'}, "当前物体没有活动材质")
            return {'CANCELLED'}

        img = node.image
        w, h = img.size
        if w <= 0 or h <= 0:
            self.report({'ERROR'}, "图像无效")
            return {'CANCELLED'}

        # 1. 读取像素并量化各通道（未启用的通道不参与计算）
        pixels = np.empty(w * h * img.channels, dtype=np.float32)
        img.pixels.foreach_get(pixels)
        data = pixels.reshape(h, w, img.channels)
        rgb = data[:, :, :3].astype(np.float32)
        has_alpha = img.channels >= 4
        alpha = data[:, :, 3].astype(np.float32) if has_alpha else np.ones((h, w), dtype=np.float32)

        q = self.quantize_levels
        q_rgb = (rgb * (q - 1)).round().astype(np.int32)
        q_a = (alpha * (q - 1)).round().astype(np.int32)

        ch = list(self.channels)
        if not has_alpha:
            ch[3] = False  # 图片无 alpha 通道时忽略 A
        if not any(ch):
            self.report({'ERROR'}, "至少需要开启一个通道")
            return {'CANCELLED'}
        r_k = q_rgb[:, :, 0] if ch[0] else np.zeros((h, w), dtype=np.int32)
        g_k = q_rgb[:, :, 1] if ch[1] else np.zeros((h, w), dtype=np.int32)
        b_k = q_rgb[:, :, 2] if ch[2] else np.zeros((h, w), dtype=np.int32)
        a_k = q_a if ch[3] else np.zeros((h, w), dtype=np.int32)

        # 组合成键（q 进制，高位优先即颜色值大小顺序）
        keys = (r_k.astype(np.int64) * q * q * q +
                g_k.astype(np.int64) * q * q +
                b_k.astype(np.int64) * q +
                a_k.astype(np.int64))

        unique_keys, counts = np.unique(keys, return_counts=True)
        if self.sort_mode == "COLOR":
            order = np.argsort(unique_keys)  # 按颜色值从小到大
        else:
            order = np.argsort(-counts)  # 按占比从高到低

        total_pixels = keys.size
        limit = min(self.max_masks, unique_keys.size)
        top_keys = unique_keys[order[:limit]]
        top_counts = counts[order[:limit]]

        # 解码各通道量化值
        r = top_keys // (q * q * q)
        g = (top_keys // (q * q)) % q
        b = (top_keys // q) % q
        a = top_keys % q
        colors = np.stack([r, g, b, a], axis=1).astype(np.float32) / (q - 1)

        mask_images = []
        hex_labels = []
        for i in range(limit):
            mask_px = np.zeros((h, w, 4), dtype=np.float32)
            mask_px[:, :, 3] = 1.0  # alpha 全 1
            match = keys == top_keys[i]
            mask_px[match, :3] = 1.0  # 目标颜色区域为白色，其余为黑色

            # 十六进制名只包含启用的通道，例如 tex_mask_FFA021
            color_255 = (colors[i] * 255.0).round().astype(np.int32)
            hex_str = "".join("{:02X}".format(color_255[ci]) for ci in range(4) if ch[ci])
            hex_labels.append(hex_str)
            mask_name = f"{img.name}_mask_{hex_str}"
            base_name = mask_name
            idx = 1
            while bpy.data.images.get(mask_name):
                mask_name = f"{base_name}.{idx:03d}"
                idx += 1

            mask_img = bpy.data.images.new(name=mask_name, width=w, height=h, alpha=True)
            mask_img.pixels.foreach_set(mask_px.ravel())
            mask_img.alpha_mode = 'CHANNEL_PACKED'
            mask_img.pack()
            # 打包后再设色彩空间，避免像素数据被重新解释
            mask_img.colorspace_settings.name = 'Non-Color'
            mask_images.append(mask_img)

            ratio = top_counts[i] / total_pixels * 100
            print(f"ID遮罩 {i + 1:2d}: {hex_str} 占比 {ratio:.2f}% -> {mask_name}")

        # 3. 创建节点组：图像遮罩经混合链合成，结果作为第一个输出
        group = bpy.data.node_groups.new(name=f"{img.name}_mask", type='ShaderNodeTree')
        # Blender 5.x 中组输入/输出节点为通用 NodeGroupInput/Output，旧版为 ShaderNode*
        try:
            group_output = group.nodes.new('NodeGroupOutput')
            group_input = group.nodes.new('NodeGroupInput')
        except RuntimeError:
            group_output = group.nodes.new('ShaderNodeGroupOutput')
            group_input = group.nodes.new('ShaderNodeGroupInput')
        group_output.location = (900, (limit - 1) * 100)
        group_input.location = (-400, (limit - 1) * 100)

        # 组输入接口：第一个混合节点的 A，默认值 000000FF（不透明黑色）
        try:
            base_sock = group.interface.new_socket(name='Base', in_out='INPUT', socket_type='NodeSocketColor')
            base_sock.default_value = (0.0, 0.0, 0.0, 1.0)
        except AttributeError:
            group.inputs.new('NodeSocketColor', 'Base')
            group.inputs[-1].default_value = (0.0, 0.0, 0.0, 1.0)

        # 输出接口：第一个为混合链最终结果，其后为各遮罩
        try:
            group.interface.new_socket(name='Mix', in_out='OUTPUT', socket_type='NodeSocketColor')
        except AttributeError:
            group.outputs.new('NodeSocketColor', 'Mix')
        for hex_str in hex_labels:
            try:
                group.interface.new_socket(name=hex_str, in_out='OUTPUT', socket_type='NodeSocketColor')
            except AttributeError:
                group.outputs.new('NodeSocketColor', hex_str)

        # 构建混合链：遮罩 → 系数，B=遮罩颜色，结果接下一个混合的 A
        prev_result = group_input.outputs['Base']
        for i, mask_img in enumerate(mask_images):
            y = (limit - 1 - i) * 300

            tex_node = group.nodes.new('ShaderNodeTexImage')
            tex_node.image = mask_img
            tex_node.location = (0, y)

            mix_node = group.nodes.new('ShaderNodeMix')
            mix_node.data_type = 'RGBA'
            mix_node.location = (300, y)
            mix_node.inputs['B'].default_value = tuple(float(c) for c in colors[i])
            group.links.new(tex_node.outputs['Color'], mix_node.inputs['Factor'])
            group.links.new(prev_result, mix_node.inputs['A'])
            prev_result = mix_node.outputs['Result']

            # 该遮罩自身的输出
            group.links.new(tex_node.outputs['Color'], group_output.inputs[hex_labels[i]])

        # 混合链最终结果连接到第一个输出
        group.links.new(prev_result, group_output.inputs['Mix'])

        # 4. 延迟创建节点组实例，位置跟随鼠标（与"新建打包图像"一致）
        def _deferred_add_group_node():
            for area in bpy.context.screen.areas:
                if area.type != 'NODE_EDITOR':
                    continue
                node_space = None
                node_region = None
                for space in area.spaces:
                    if space.type == 'NODE_EDITOR':
                        node_space = space
                for region in area.regions:
                    if region.type == 'WINDOW':
                        node_region = region
                if not node_space or not node_region:
                    continue

                cur_mat = bpy.context.active_object.active_material
                if not cur_mat:
                    return None
                if not cur_mat.use_nodes:
                    cur_mat.use_nodes = True
                mat_nodes = cur_mat.node_tree.nodes

                for n in mat_nodes:
                    n.select = False

                group_node = mat_nodes.new('ShaderNodeGroup')
                group_node.node_tree = group
                group_node.location = node_space.cursor_location
                group_node.select = True
                mat_nodes.active = group_node
                return None
            return None

        bpy.app.timers.register(_deferred_add_group_node, first_interval=0.05)

        self.report({'INFO'}, f"已分离 {limit} 个ID遮罩并创建节点组")
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
        col.operator(XQFA_OT_detect_normal_format.bl_idname, icon='NODE_SEL')
        col.operator(XQFA_OT_ensure_material.bl_idname, icon='MATERIAL_DATA')
        col.operator(XQFA_OT_viewer_to_material.bl_idname, icon='IMAGE_DATA')
        col.operator(XQFA_OT_create_packed_image.bl_idname, icon='ADD')
        col.operator(XQFA_OT_extract_id_masks.bl_idname, icon='FILTER')

classes = (
    XQFA_OT_detect_normal_format,
    XQFA_OT_ensure_material,
    XQFA_OT_viewer_to_material,
    XQFA_OT_create_packed_image,
    XQFA_OT_extract_id_masks,
    XQFA_PT_material_tools,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

