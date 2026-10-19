# type: ignore
import bpy
import mathutils
from mathutils import Vector
import math

class DATA_PT_uv_map_tools(bpy.types.Panel):
    bl_label = "UV贴图"
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
        
        # 添加操作按钮
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(scene, "uv_map_target_index", text="")
        row.operator(O_SetActiveUVMaps.bl_idname, text="", icon="RESTRICT_SELECT_OFF")
        row.operator(O_SetRenderUVMaps.bl_idname, text="", icon="RESTRICT_RENDER_OFF")
        row.operator(O_RemoveUVMaps.bl_idname, text="", icon="TRASH")
        row.operator(O_AddUVMaps.bl_idname, text="", icon="ADD")
        col.separator()
        col.operator(XQFA_OT_OctahedralUV.bl_idname, icon='UV')
        col.operator(XQFA_OT_ScaleUVIslands.bl_idname, icon='UV_DATA')
        col.operator(XQFA_OT_ProjectUVFromView.bl_idname, icon='UV_DATA')


class O_AddUVMaps(bpy.types.Operator):
    bl_idname = "xqfa.add_uv_map"
    bl_label = "添加UV"
    bl_description = "在顶部添加TEXCOORD.xy格式的UV贴图"

    @staticmethod
    def _prepend_uv_layers(uv_layers, count):
        """在UV贴图列表顶部添加count个新层，原有层顺序不变向下顺延"""
        # 快照原有层（名称、渲染状态、UV数据）
        original = [(l.name, l.active_render, [v.uv.copy() for v in l.data]) for l in uv_layers]
        active_name = uv_layers.active.name if uv_layers.active else None
        # 快照当前活动UV的数据，用于填充新增层（新增层内容与活动UV相同）
        active_data = [v.uv.copy() for v in uv_layers.active.data] if uv_layers.active else None

        # 1. 删除所有原有层（使列表清空，后续新层自然排在最前）
        # 必须从后往前按索引删除：list(uv_layers) 取得的层引用在删除后即失效，
        # 继续用失效引用删除会删错层并抛出 "UV map ... not found"，导致UV层被破坏
        for i in range(len(uv_layers) - 1, -1, -1):
            uv_layers.remove(uv_layers[i])

        # 2. 创建新层并复制活动UV的数据
        for i in range(count):
            name = f"TEXCOORD{i}.xy" if i > 0 else "TEXCOORD.xy"
            new_layer = uv_layers.new(name=name)
            if new_layer is None:
                raise RuntimeError("创建UV贴图失败：可能已达数量上限或网格没有面")
            if active_data is not None:
                for li, uv in enumerate(active_data):
                    new_layer.data[li].uv = uv

        # 3. 按原顺序重建原有层
        for src_name, src_render, uv_list in original:
            copied = uv_layers.new(name=src_name)
            if copied is None:
                raise RuntimeError("创建UV贴图失败：可能已达数量上限或网格没有面")
            for li, uv in enumerate(uv_list):
                copied.data[li].uv = uv
            copied.active_render = src_render

        # 4. 恢复活动层
        if active_name and active_name in uv_layers:
            uv_layers.active = uv_layers[active_name]

    def execute(self, context):
        scene = context.scene
        target_index = scene.uv_map_target_index
        count = target_index + 1

        processed_objects = 0
        added_maps = 0

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue

            processed_objects += 1
            uv_layers = obj.data.uv_layers
            # Blender 每个网格最多 8 个 UV 贴图（MAX_MTFACE 限制）
            if len(uv_layers) + count > 8:
                self.report({'WARNING'}, f"物体 {obj.name} 添加UV失败：Blender 每网格最多 8 个UV贴图（当前 {len(uv_layers)} 个，还需 {count} 个）")
                continue
            if len(obj.data.loops) == 0:
                self.report({'WARNING'}, f"物体 {obj.name} 添加UV失败：网格没有面")
                continue
            try:
                self._prepend_uv_layers(uv_layers, count)
            except RuntimeError as e:
                self.report({'WARNING'}, f"物体 {obj.name} 添加UV失败：{e}")
                continue
            added_maps += count

        # 强制刷新所有区域
        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"处理完成: {processed_objects}个物体, 添加{added_maps}个")
        return {'FINISHED'}

class O_SetActiveUVMaps(bpy.types.Operator):
    bl_idname = "xqfa.uv_map_set_active"
    bl_label = "活动"
    bl_description = "将所有选中物体的活动UV设置为指定索引"
    
    def execute(self, context):
        scene = context.scene
        target_index = scene.uv_map_target_index
        
        processed_objects = 0
        set_active_count = 0
        
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
                
            processed_objects += 1
            uv_layers = obj.data.uv_layers
            
            if target_index < 0 or target_index >= len(uv_layers):
                self.report({'WARNING'}, f"物体 {obj.name} 的UV索引 {target_index} 超出范围")
                continue
                
            uv_layers.active = uv_layers[target_index]
            set_active_count += 1
        
        # 强制刷新所有区域
        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"处理完成: {processed_objects}个物体, 设置了{set_active_count}个活动UV")
        return {'FINISHED'}

class O_SetRenderUVMaps(bpy.types.Operator):
    bl_idname = "xqfa.uv_map_set_render"
    bl_label = "渲染"
    bl_description = "将所有选中物体的渲染UV设置为指定索引"
    
    def execute(self, context):
        scene = context.scene
        target_index = scene.uv_map_target_index
        
        processed_objects = 0
        set_render_count = 0
        
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
                
            processed_objects += 1
            uv_layers = obj.data.uv_layers
            
            if target_index < 0 or target_index >= len(uv_layers):
                self.report({'WARNING'}, f"物体 {obj.name} 的UV索引 {target_index} 超出范围")
                continue
                
            uv_layers[target_index].active_render = True
            # 确保其他UV层不激活渲染
            for i, uv_layer in enumerate(uv_layers):
                if i != target_index:
                    uv_layer.active_render = False
            set_render_count += 1
        
        # 强制刷新所有区域
        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"处理完成: {processed_objects}个物体, 设置了{set_render_count}个渲染UV")
        return {'FINISHED'}

class O_RemoveUVMaps(bpy.types.Operator):
    bl_idname = "xqfa.uv_map_remove"
    bl_label = "删除"
    bl_description = "删除指定索引的UV贴图"
    
    def execute(self, context):
        scene = context.scene
        target_index = scene.uv_map_target_index
        
        processed_objects = 0
        removed_maps = 0
        
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
                
            processed_objects += 1
            uv_layers = obj.data.uv_layers
            
            if target_index < 0 or target_index >= len(uv_layers):
                self.report({'WARNING'}, f"物体 {obj.name} 的UV索引 {target_index} 超出范围")
                continue

            # 检查要删除的层是否是活动层
            target_is_active = (uv_layers.active == uv_layers[target_index])

            # 记录当前活动层索引（用于重新设置）
            current_active_index = uv_layers[:].index(uv_layers.active) if uv_layers.active else -1
            
            # 删除指定索引的UV贴图
            uv_layer_to_remove = uv_layers[target_index]
            uv_layers.remove(uv_layer_to_remove)
            removed_maps += 1
            
            # 确保活动UV和渲染UV有效
            if len(uv_layers) > 0 and target_is_active:
                new_active_index = min(current_active_index, len(uv_layers) - 1)
                if new_active_index >= 0:
                    uv_layers.active = uv_layers[new_active_index]
                else:
                    uv_layers.active = uv_layers[0]

        
        # 强制刷新所有区域
        for area in context.screen.areas:
            area.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"处理完成: {processed_objects}个物体, 删除了{removed_maps}个UV贴图")
        return {'FINISHED'}

class XQFA_OT_ProjectUVFromView(bpy.types.Operator):
    """将选中物体的活动UV设为TEXCOORD3.xy并按当前视角投影"""
    bl_idname = "xqfa.uv_project_from_view"
    bl_label = "视角投影UV"
    bl_description = ("对所有选中物体\n"
                      "将活动UV设置为TEXCOORD3.xy（没有则新建）\n"
                      "进入编辑模式全选面，并按当前视角投影UV\n"
                      "整体计算UV包围框，按高度等比缩放至0.95并移至UV中心(0.5, 0.5)")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and len(context.selected_objects) > 0

    def execute(self, context):
        # 确保处于物体模式（数据一致）
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        target_name = "TEXCOORD3.xy"
        project_objs = []

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            uv_layers = obj.data.uv_layers
            if target_name in uv_layers:
                uv_layers.active = uv_layers[target_name]
            else:
                new_layer = uv_layers.new(name=target_name)
                if new_layer is None:
                    self.report({'WARNING'}, f"物体 {obj.name} 新建 {target_name} 失败：网格没有面或已达8个UV上限")
                    continue
                uv_layers.active = new_layer
            project_objs.append(obj)

        if not project_objs:
            self.report({'WARNING'}, "没有可处理的网格物体")
            return {'CANCELLED'}

        # project_from_view 依赖3D视口的区域数据计算投影矩阵，
        # 面板按钮点击时 context.region 是UI区域，需临时覆盖为3D视口的WINDOW区域
        screen = context.screen
        area = context.area
        if area is None or area.type != 'VIEW_3D':
            area = next((a for a in screen.areas if a.type == 'VIEW_3D'), None) if screen else None
        if area is None:
            self.report({'WARNING'}, "找不到3D视口，无法按视角投影")
            return {'CANCELLED'}
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)

        # 进入（多物体）编辑模式，全选所有面，按当前视角投影UV
        context.view_layer.objects.active = project_objs[0]
        for obj in project_objs:
            obj.select_set(True)
        with context.temp_override(area=area, region=region):
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.project_from_view()
            bpy.ops.object.mode_set(mode='OBJECT')

        # 整体计算UV包围框：按高度等比缩放至0.95，并把包围框中心移到UV中心(0.5, 0.5)
        if not self._fit_uv_joint(project_objs):
            self.report({'WARNING'}, "UV包围框高度为0或无UV数据，已跳过缩放居中")

        # 强制刷新所有区域
        for a in context.screen.areas:
            a.tag_redraw()
        context.view_layer.update()
        self.report({'INFO'}, f"处理完成: {len(project_objs)}个物体, 活动UV已设为{target_name}, 视角投影并缩放0.95居中")
        return {'FINISHED'}

    @staticmethod
    def _fit_uv_joint(objs, target_height=0.95, center=(0.5, 0.5)):
        """将多个物体的活动UV视为整体：等比缩放使包围框高度为target_height，并把包围框中心移到center"""
        flats = []
        for obj in objs:
            uv_data = obj.data.uv_layers.active.data
            count = len(uv_data)
            if count == 0:
                continue
            flat = [0.0] * (count * 2)
            uv_data.foreach_get("uv", flat)
            flats.append((uv_data, flat))

        if not flats:
            return False

        min_u = min_v = math.inf
        max_u = max_v = -math.inf
        for _, flat in flats:
            for i in range(0, len(flat), 2):
                u = flat[i]
                v = flat[i + 1]
                if u < min_u:
                    min_u = u
                if u > max_u:
                    max_u = u
                if v < min_v:
                    min_v = v
                if v > max_v:
                    max_v = v

        box_h = max_v - min_v
        if box_h < 1e-9:
            return False

        scale = target_height / box_h
        center_u = (min_u + max_u) * 0.5
        center_v = (min_v + max_v) * 0.5

        for uv_data, flat in flats:
            for i in range(0, len(flat), 2):
                flat[i] = (flat[i] - center_u) * scale + center[0]
                flat[i + 1] = (flat[i + 1] - center_v) * scale + center[1]
            uv_data.foreach_set("uv", flat)
        return True

def unit_vector_to_octahedron(n):
    """
    Converts a unit vector to octahedron coordinates.
    n is a mathutils.Vector
    """
    # 确保输入是单位向量
    if n.length_squared > 1e-10:
        n.normalize()
    else:
        return Vector((0.0, 0.0))
    
    # 计算L1范数
    l1_norm = abs(n.x) + abs(n.y) + abs(n.z)
    if l1_norm < 1e-10:
        return Vector((0.0, 0.0))
    
    # 投影到八面体平面
    x = n.x / l1_norm
    y = n.y / l1_norm
    
    # 负半球映射（仅在z<0时应用）
    if n.z < 0:
        # 使用精确的符号函数
        sign_x = math.copysign(1.0, x)
        sign_y = math.copysign(1.0, y)
        
        # 原始映射公式（保留在z=0处的良好行为）
        new_x = (1.0 - abs(y)) * sign_x
        new_y = (1.0 - abs(x)) * sign_y
        
        # 直接应用新坐标（移除过渡插值）
        x = new_x
        y = new_y
    
    return Vector((x, y))

def calc_smooth_normals(mesh):
    """计算平滑法线（角度加权平均）"""
    vertex_normals = {}
    
    # 使用顶点索引作为键（避免浮点精度问题）
    for i, vert in enumerate(mesh.vertices):
        vertex_normals[i] = Vector((0, 0, 0))
    
    # 计算每个面的法线并加权累加到顶点
    for poly in mesh.polygons:
        verts = [mesh.vertices[i] for i in poly.vertices]
        face_normal = poly.normal
        
        for i, vert in enumerate(verts):
            # 获取相邻边向量
            v1 = verts[(i+1) % len(verts)].co - vert.co
            v2 = verts[(i-1) % len(verts)].co - vert.co
            
            # 计算角度权重
            v1_len = v1.length
            v2_len = v2.length
            if v1_len > 1e-6 and v2_len > 1e-6:
                v1.normalize()
                v2.normalize()
                weight = math.acos(max(-1.0, min(1.0, v1.dot(v2))))
            else:
                weight = 0.0
            
            # 累加加权法线
            vertex_normals[vert.index] += face_normal * weight
    
    # 归一化法线
    for idx in vertex_normals:
        if vertex_normals[idx].length > 1e-6:
            vertex_normals[idx].normalize()
    
    return vertex_normals

class XQFA_OT_OctahedralUV(bpy.types.Operator):
    """生成切线空间的八面体UV映射"""
    bl_idname = "xqfa.octahedral_uv"
    bl_label = "平滑法线-八面体UV"
    bl_description = ("对所有选中物体\n"
    "平滑法线在切线空间的坐标，投射八面体展开平面\n"
    "存储在TEXCOORD1\n"
    "为了计算切线空间，必须要有一个正常展开的uv")
    bl_options = {'REGISTER', 'UNDO'}
    
    
    @classmethod
    def poll(cls, context):
        """检查是否可以选择网格物体"""
        return context.selected_objects is not None and len(context.selected_objects) > 0
    
    def execute(self, context):
        """执行操作"""
        selected_objects = context.selected_objects
        processed_count = 0
        
        for obj in selected_objects:
            if self.process_object(obj):
                processed_count += 1
        
        # 更新显示
        context.view_layer.update()
        
        if processed_count > 0:
            self.report({'INFO'}, f"切线空间八面体UV映射完成！共处理 {processed_count} 个网格物体")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "没有处理任何网格物体，请确保选中了网格物体")
            return {'CANCELLED'}
    
    def process_object(self, obj):
        """处理单个网格物体"""
        if obj.type != 'MESH':
            return False
            
        mesh = obj.data
        
        # 确保在对象模式（数据一致）
        if bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # 操作前将活动UV设置为第一个（索引0）
        if len(mesh.uv_layers) > 0:
            mesh.uv_layers.active_index = 0
        
        # 计算平滑法线
        smooth_normals = calc_smooth_normals(mesh)
        
        # 确保网格有UV层（计算切线需要）
        if len(mesh.uv_layers) == 0:
            mesh.uv_layers.new(name="UVMap")
        
        # 计算切线空间（TBN矩阵）
        mesh.calc_tangents()
        
        # 创建/获取UV层
        uv_layer_name = "TEXCOORD1.xy"
        if uv_layer_name in mesh.uv_layers:
            uv_layer = mesh.uv_layers[uv_layer_name]
        else:
            uv_layer = mesh.uv_layers.new(name=uv_layer_name)
        
        # 处理每个面的每个顶点
        for poly in mesh.polygons:
            for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                loop = mesh.loops[loop_idx]
                vertex_idx = loop.vertex_index
                
                # 获取平滑法线
                normal = smooth_normals[vertex_idx]

                # 构建TBN矩阵（切线空间到模型空间的变换）
                tbn_matrix = mathutils.Matrix((
                    loop.tangent,
                    loop.bitangent,
                    loop.normal
                )).transposed() # 转置以从行向量变为列向量
                
                # 检查矩阵是否可逆
                try:
                    # 尝试计算逆矩阵
                    tbn_inverse = tbn_matrix.inverted()
                    
                    # 将法线从模型空间转换到切线空间
                    tangent_normal = tbn_inverse @ normal
                    tangent_normal.normalize()
                except ValueError:
                    # 矩阵不可逆时的回退方案
                    print(f"警告: 顶点 {vertex_idx} 的TBN矩阵不可逆，使用默认法线")
                    
                    tangent_normal = Vector((0, 0, 1))  # 默认使用Z轴作为法线
                
                # 八面体投影
                oct_coords = unit_vector_to_octahedron(tangent_normal)
                
                # 设置UV
                u = oct_coords.x
                v = oct_coords.y + 1.0
                uv_layer.data[loop_idx].uv = (u, v)
        
        # 释放切线数据
        mesh.free_tangents()
        
        return True

class XQFA_OT_ScaleUVIslands(bpy.types.Operator):
    """将选中物体的活动UV中每个孤岛缩放至0-1范围"""
    bl_idname = "xqfa.scale_uv_islands"
    bl_label = "UV孤岛归一化"
    bl_description = "将选中物体的活动UV中每个孤岛独立缩放至0-1范围"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and len(context.selected_objects) > 0

    @staticmethod
    def get_uv_island_bbox(uv_layer, loop_indices):
        """计算一个UV孤岛的边界框，返回(min_u, min_v, max_u, max_v)"""
        min_u = float('inf')
        min_v = float('inf')
        max_u = float('-inf')
        max_v = float('-inf')

        for loop_idx in loop_indices:
            uv = uv_layer.data[loop_idx].uv
            if uv.x < min_u:
                min_u = uv.x
            if uv.y < min_v:
                min_v = uv.y
            if uv.x > max_u:
                max_u = uv.x
            if uv.y > max_v:
                max_v = uv.y

        return min_u, min_v, max_u, max_v

    @staticmethod
    def scale_island_to_01(uv_layer, loop_indices, min_u, min_v, max_u, max_v):
        """将一个UV孤岛缩放并平移至0-1范围"""
        range_u = max_u - min_u
        range_v = max_v - min_v

        # 避免除以零
        if range_u < 1e-8:
            range_u = 1.0
        if range_v < 1e-8:
            range_v = 1.0

        for loop_idx in loop_indices:
            uv = uv_layer.data[loop_idx].uv
            uv.x = (uv.x - min_u) / range_u
            uv.y = (uv.y - min_v) / range_v

    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not selected_objects:
            self.report({'WARNING'}, "未选中任何网格物体")
            return {'CANCELLED'}

        total_islands = 0

        for obj in selected_objects:
            mesh = obj.data
            uv_layer = mesh.uv_layers.active

            if uv_layer is None:
                self.report({'WARNING'}, f"物体 {obj.name} 没有活动UV层，已跳过")
                continue

            # 收集UV孤岛：通过面的连接性分组
            # 使用并查集(Union-Find)来识别UV孤岛
            num_loops = len(mesh.loops)
            parent = list(range(num_loops))

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def union(a, b):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb

            # 同一个面的loop属于同一孤岛
            for poly in mesh.polygons:
                loops = list(range(poly.loop_start, poly.loop_start + poly.loop_total))
                for i in range(len(loops) - 1):
                    union(loops[i], loops[i + 1])

            # 共享相同UV坐标（同一顶点+相同UV位置）的loop也属于同一孤岛
            # 按顶点索引分组
            vert_loops = {}
            for loop in mesh.loops:
                vi = loop.vertex_index
                if vi not in vert_loops:
                    vert_loops[vi] = []
                vert_loops[vi].append(loop.index)

            for vi, loop_ids in vert_loops.items():
                # 按UV位置分组（容差比较）
                groups = []
                for lid in loop_ids:
                    uv = uv_layer.data[lid].uv
                    placed = False
                    for group in groups:
                        ref_uv = uv_layer.data[group[0]].uv
                        if abs(uv.x - ref_uv.x) < 1e-6 and abs(uv.y - ref_uv.y) < 1e-6:
                            group.append(lid)
                            placed = True
                            break
                    if not placed:
                        groups.append([lid])
                # 同一UV位置的loops属于同一孤岛
                for group in groups:
                    for i in range(len(group) - 1):
                        union(group[i], group[i + 1])

            # 按根节点分组得到孤岛
            islands = {}
            for i in range(num_loops):
                root = find(i)
                if root not in islands:
                    islands[root] = []
                islands[root].append(i)

            # 对每个孤岛计算边界框并缩放至0-1
            obj_island_count = 0
            for root, loop_indices in islands.items():
                min_u, min_v, max_u, max_v = self.get_uv_island_bbox(uv_layer, loop_indices)
                # 跳过退化的孤岛
                if (max_u - min_u) < 1e-8 and (max_v - min_v) < 1e-8:
                    continue
                self.scale_island_to_01(uv_layer, loop_indices, min_u, min_v, max_u, max_v)
                obj_island_count += 1

            total_islands += obj_island_count

        if total_islands > 0:
            self.report({'INFO'}, f"已将 {total_islands} 个UV孤岛缩放至0-1范围")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "未找到可处理的UV孤岛")
            return {'CANCELLED'}


classes = (
    DATA_PT_uv_map_tools,
    O_AddUVMaps,
    O_SetActiveUVMaps,
    O_SetRenderUVMaps,
    O_RemoveUVMaps,
    XQFA_OT_OctahedralUV,
    XQFA_OT_ScaleUVIslands,
    XQFA_OT_ProjectUVFromView,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # 添加场景属性用于存储目标UV索引
    bpy.types.Scene.uv_map_target_index = bpy.props.IntProperty(
        name="目标UV索引",
        description="要设置的活动/渲染UV的索引",
        default=0,
        min=0,
        max=31
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.uv_map_target_index