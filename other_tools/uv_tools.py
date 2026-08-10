# type: ignore
import math
import time
import bpy
import bmesh


# Blender 5.0+ 移除了 BMLoopUV.select/select_edge，改用 BMLoop.uv_select_vert/uv_select_edge
# 以下辅助函数兼容两种版本（4.x 的 UV 选择按层存储，5.0+ 全局共享）

def uv_vert_selected(loop, uv_layer):
    """读取UV顶点的选择状态"""
    if hasattr(loop, 'uv_select_vert'):
        return loop.uv_select_vert
    return loop[uv_layer].select


def uv_vert_select_set(loop, uv_layer, value):
    """设置UV顶点的选择状态"""
    if hasattr(loop, 'uv_select_vert'):
        loop.uv_select_vert = value
    else:
        loop[uv_layer].select = value


def uv_edge_select_set(loop, uv_layer, value):
    """设置UV边的选择状态"""
    if hasattr(loop, 'uv_select_edge'):
        loop.uv_select_edge = value
    else:
        loop[uv_layer].select_edge = value


def uv_edge_selected(loop, uv_layer):
    """读取UV边的选择状态"""
    if hasattr(loop, 'uv_select_edge'):
        return loop.uv_select_edge
    return loop[uv_layer].select_edge


def uv_vert_pinned(loop, uv_layer):
    """读取UV顶点的钉固状态"""
    if hasattr(loop, 'uv_pin_vert'):
        return loop.uv_pin_vert
    return loop[uv_layer].pin_uv


def uv_vert_pin_set(loop, uv_layer, value):
    """设置UV顶点的钉固状态"""
    if hasattr(loop, 'uv_pin_vert'):
        loop.uv_pin_vert = value
    else:
        loop[uv_layer].pin_uv = value


def _select_linked_uv(bm, uv_layer, use_sync=False):
    """用bmesh API实现UV选择扩展（类似Ctrl+L），避免bpy.ops.uv.select_linked在重合边时卡死"""
    # 一次遍历：构建UV邻接图 + 收集初始选中节点（跳过隐藏面）
    adj = {}
    selected_keys = set()
    for f in bm.faces:
        if f.hide:
            continue
        for l in f.loops:
            uv = l[uv_layer].uv
            k = (round(uv.x, 6), round(uv.y, 6))
            is_sel = l.vert.select if use_sync else uv_vert_selected(l, uv_layer)
            if is_sel:
                selected_keys.add(k)
            ln = l.link_loop_next
            uv2 = ln[uv_layer].uv
            k2 = (round(uv2.x, 6), round(uv2.y, 6))
            if k not in adj:
                adj[k] = set()
            adj[k].add(k2)
            if k2 not in adj:
                adj[k2] = set()
            adj[k2].add(k)
    if not selected_keys:
        return
    # BFS扩展选中节点
    visited = set(selected_keys)
    queue = list(selected_keys)
    while queue:
        cur = queue.pop()
        for nb in adj.get(cur, ()):
            if nb not in visited:
                visited.add(nb)
                queue.append(nb)
    # 设置选择状态
    for f in bm.faces:
        if f.hide:
            continue
        for l in f.loops:
            uv = l[uv_layer].uv
            k = (round(uv.x, 6), round(uv.y, 6))
            if k in visited:
                if use_sync:
                    l.vert.select = True
                else:
                    uv_vert_select_set(l, uv_layer, True)


# --- 界面面板 (UV 编辑器) ---

class XQFA_PT_UVMiscTools(bpy.types.Panel):
    bl_label = "UV 工具"
    bl_idname = "XQFA_PT_uv_misc_tools"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        # UV 编辑器中始终显示，不依赖主面板的子面板切换
        return True

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="UV重力布料模拟")
        box.operator("xqfa.gravity_uv", text="选中孤岛受重力下坠", icon='MOD_CLOTH')

        box = layout.box()
        box.label(text="UV边链拉直")
        row = box.row(align=True)
        op = row.operator("xqfa.straighten_uv_chain", text="水平拉直")
        op.direction = 'HORIZONTAL'
        op = row.operator("xqfa.straighten_uv_chain", text="垂直拉直")
        op.direction = 'VERTICAL'

        box = layout.box()
        box.label(text="UV边链对齐")
        row = box.row(align=True)
        op = row.operator("xqfa.straighten_uv_chain", text="水平对齐")
        op.direction = 'ALIGN_HORIZONTAL'
        op = row.operator("xqfa.straighten_uv_chain", text="垂直对齐")
        op.direction = 'ALIGN_VERTICAL'


# --- UV重力布料模拟（见 .vibe-coding/算法.md） ---

class XQFA_OT_GravityUV(bpy.types.Operator):
    """对选中UV孤岛施加重力布料模拟：顶部顶点钉住，其余顶点受重力自然下坠"""
    bl_idname = "xqfa.gravity_uv"
    bl_label = "UV重力"
    bl_description = ("把选中UV孤岛当作布料：顶部顶点钉住，其余顶点受重力下坠，"
                      "网格边作为弹簧保持UV形状，面三角形面积约束防止拉伸变形与翻转\n"
                      "(可用 Ctrl+Z 撤销)")
    bl_options = {'REGISTER', 'UNDO'}

    steps: bpy.props.IntProperty(
        name="模拟步数",
        description="布料下坠模拟的迭代次数，越大越接近最终形态",
        default=150, min=30, max=500,
    )
    pin_ratio: bpy.props.FloatProperty(
        name="顶部钉住比例",
        description="孤岛顶部高度占比内的顶点被钉住不动，其余顶点向下坠落",
        default=0.1, min=0.0, max=0.9, precision=2,
    )
    gravity: bpy.props.FloatProperty(
        name="重力强度",
        description="重力倍率，越大下坠越明显，同时变形也会更明显",
        default=1.0, min=0.0, max=5.0, precision=2,
    )
    spring_stiffness: bpy.props.FloatProperty(
        name="弹簧刚度",
        description="网格边弹簧抵抗拉伸的强度，越高形状保持越好，变形越小",
        default=1.0, min=0.1, max=1.0, precision=2,
    )
    area_stiffness: bpy.props.FloatProperty(
        name="面积保持",
        description="保持每个面UV面积不变的约束强度，防止孤岛被拉伸变形（越大面积保持越好）",
        default=0.8, min=0.0, max=1.0, precision=2,
    )
    solver_iters: bpy.props.IntProperty(
        name="约束迭代",
        description="每步模拟中弹簧与面积约束的求解次数，越大约束越精确、变形越小，但更慢",
        default=10, min=1, max=50,
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            self.report({'WARNING'}, "当前物体没有UV层")
            return {'CANCELLED'}

        # 先扩展选择到整个孤岛（类似Ctrl+L），只需选中一个顶点即可操作整个孤岛
        _select_linked_uv(bm, uv_layer, context.scene.tool_settings.use_uv_select_sync)

        # --- 收集选中loop（即当前孤岛），同步模式回退读取网格顶点选择 ---
        sel_loops = []
        island_faces = set()
        for f in bm.faces:
            if f.hide:
                continue
            for l in f.loops:
                if uv_vert_selected(l, uv_layer):
                    sel_loops.append(l)
                    island_faces.add(f)
        if not sel_loops and context.scene.tool_settings.use_uv_select_sync:
            for f in bm.faces:
                if f.hide:
                    continue
                for l in f.loops:
                    if l.vert.select:
                        sel_loops.append(l)
                        island_faces.add(f)
        if not sel_loops:
            self.report({'WARNING'}, "请在UV编辑器中选择一个UV孤岛")
            return {'CANCELLED'}

        # --- UV节点表：坐标相同（容差内）视为同一节点 ---
        node_pos = {}          # 节点id -> (u, v)
        node_key_map = {}      # (round(u,6), round(v,6)) -> 节点id
        loop_node = {}         # loop -> 节点id

        def get_node(u, v):
            key = (round(u, 6), round(v, 6))
            if key not in node_key_map:
                nid = len(node_pos)
                node_key_map[key] = nid
                node_pos[nid] = (u, v)
            return node_key_map[key]

        for l in sel_loops:
            loop_node[l] = get_node(l[uv_layer].uv.x, l[uv_layer].uv.y)

        # --- 弹簧：网格边 + 面内所有顶点两两相连（防止UV翻转） ---
        springs = {}           # (min节点, max节点) -> (a, b, 原长)

        def add_spring(a, b):
            key = (min(a, b), max(a, b))
            if a == b or key in springs:
                return
            ua, va = node_pos[a]
            ub, vb = node_pos[b]
            springs[key] = (a, b, math.hypot(ub - ua, vb - va))

        # 每个面内部两两建弹簧：三角形即三条边，四边形多两条对角线，阻止面翻转
        for f in island_faces:
            fnodes = [loop_node[l] for l in f.loops if l in loop_node]
            for i in range(len(fnodes)):
                for j in range(i + 1, len(fnodes)):
                    add_spring(fnodes[i], fnodes[j])

        # 边界边：选中loop与其下一条loop若都在选中区，补一条弹簧
        for l in sel_loops:
            ln = l.link_loop_next
            if ln in loop_node:
                add_spring(loop_node[l], loop_node[ln])

        if not springs:
            self.report({'WARNING'}, "选中的UV没有可用的边连接")
            return {'CANCELLED'}
        spring_list = list(springs.values())

        # --- 面积约束表：每个完整选中的面扇形三角化，记录三角形原始双倍面积 ---
        # 求解时把每个三角形的双倍面积拉回原值，从而保持面的UV面积并防止翻转
        tri_list = []   # (n0, n1, n2, 原始双倍面积)
        for f in island_faces:
            fnodes = [loop_node[l] for l in f.loops if l in loop_node]
            if len(fnodes) < 3 or len(fnodes) != len(f.loops):
                continue   # 只约束完全被选中的面
            for i in range(1, len(fnodes) - 1):
                a, b, c = fnodes[0], fnodes[i], fnodes[i + 1]
                ax, ay = node_pos[a]
                bx, by = node_pos[b]
                cx, cy = node_pos[c]
                da = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
                if abs(da) > 1e-12:
                    tri_list.append((a, b, c, da))

        # --- 按连通分量求每个孤岛自己的顶部，钉住顶部顶点 ---
        node_adj = {nid: [] for nid in node_pos}
        for (a, b, _l0) in spring_list:
            node_adj[a].append(b)
            node_adj[b].append(a)

        pinned = set()
        seen = set()
        for nid in node_pos:
            if nid in seen:
                continue
            comp = []
            stack = [nid]
            seen.add(nid)
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for nb in node_adj[cur]:
                    if nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            vmax = max(node_pos[c][1] for c in comp)
            vmin = min(node_pos[c][1] for c in comp)
            h = max(vmax - vmin, 1e-9)
            for c in comp:
                if node_pos[c][1] >= vmax - self.pin_ratio * h:
                    pinned.add(c)

        # --- PBD Verlet 布料模拟 ---
        all_u = [p[0] for p in node_pos.values()]
        all_v = [p[1] for p in node_pos.values()]
        size = max(max(all_u) - min(all_u), max(all_v) - min(all_v), 1e-6)
        g = 0.004 * size * self.gravity        # 每步重力(UV单位)，默认下坠约4-5%岛高
        damp = 0.97                            # 速度阻尼
        stiffness = self.spring_stiffness      # 弹簧刚度
        a_stiff = self.area_stiffness          # 面积约束刚度

        # 大孤岛自动降低迭代次数，避免卡顿
        heavy = max(len(node_pos), len(spring_list))
        if heavy > 120000:
            steps, solver_iters = 60, 1
        elif heavy > 40000:
            steps, solver_iters = 100, 2
        else:
            steps, solver_iters = self.steps, self.solver_iters

        orig = dict(node_pos)
        prev = dict(node_pos)
        pos = dict(node_pos)

        for _step in range(steps):
            # 重力 + 惯性（Verlet积分）
            new_pos = {}
            for nid, (u, v) in pos.items():
                if nid in pinned:
                    new_pos[nid] = orig[nid]
                    continue
                vx = (u - prev[nid][0]) * damp
                vy = (v - prev[nid][1]) * damp
                new_pos[nid] = (u + vx, v + vy - g)
            # 弹簧约束 + 面积约束求解（保持UV形状，防止拉伸变形与翻转）
            for _it in range(solver_iters):
                for (a, b, l0) in spring_list:
                    ua, va = new_pos[a]
                    ub, vb = new_pos[b]
                    dx = ub - ua
                    dy = vb - va
                    d = math.hypot(dx, dy)
                    if d < 1e-9:
                        continue
                    move = (d - l0) / d * 0.5 * stiffness
                    new_pos[a] = (ua + dx * move, va + dy * move)
                    new_pos[b] = (ub - dx * move, vb - dy * move)
                if a_stiff > 0 and tri_list:
                    for (n0, n1, n2, da0) in tri_list:
                        ax, ay = new_pos[n0]
                        bx, by = new_pos[n1]
                        cx, cy = new_pos[n2]
                        # 双倍面积的梯度投影：把当前面积拉回原始值
                        g_a = (by - cy, cx - bx)
                        g_b = (cy - ay, ax - cx)
                        g_c = (ay - by, bx - ax)
                        denom = (g_a[0] * g_a[0] + g_a[1] * g_a[1]
                                 + g_b[0] * g_b[0] + g_b[1] * g_b[1]
                                 + g_c[0] * g_c[0] + g_c[1] * g_c[1])
                        if denom < 1e-12:
                            continue
                        da = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
                        lam = (da - da0) / denom * a_stiff
                        new_pos[n0] = (ax - lam * g_a[0], ay - lam * g_a[1])
                        new_pos[n1] = (bx - lam * g_b[0], by - lam * g_b[1])
                        new_pos[n2] = (cx - lam * g_c[0], cy - lam * g_c[1])
            for nid in pinned:
                new_pos[nid] = orig[nid]
            prev, pos = pos, new_pos

        # --- 写回UV坐标 ---
        for l in sel_loops:
            l[uv_layer].uv = pos[loop_node[l]]

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"UV重力完成: {len(node_pos)}个顶点, {len(spring_list)}条弹簧, "
                              f"{len(tri_list)}个面积三角形, {steps}步")
        return {'FINISHED'}


# --- UV边链拉直：把选中单向相连的UV边链拉直为水平/垂直线 ---

class XQFA_OT_StraightenUVChain(bpy.types.Operator):
    """把选中的一串UV边拉直为水平线或垂直线，锚点不动、点间距离不变"""
    bl_idname = "xqfa.straighten_uv_chain"
    bl_label = "UV边链拉直"
    bl_description = ("把选中的一条UV边链拉直或对齐：\n"
                      "垂直拉直：所有点落到同一条垂直线上，最上方点保持不动，距离保持\n"
                      "水平拉直：所有点落到同一条水平线上，最左边点保持不动，距离保持\n"
                      "垂直对齐：所有点的U坐标统一为锚点U坐标，V坐标不变\n"
                      "水平对齐：所有点的V坐标统一为锚点V坐标，U坐标不变")
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(
        name="方向",
        description="拉直或对齐的方向",
        items=[
            ('HORIZONTAL', "水平拉直", "拉直为一条水平线，最左边点保持不动，距离保持"),
            ('VERTICAL', "垂直拉直", "拉直为一条垂直线，最上方点保持不动，距离保持"),
            ('ALIGN_HORIZONTAL', "水平对齐", "所有点的V坐标统一，U坐标不变"),
            ('ALIGN_VERTICAL', "垂直对齐", "所有点的U坐标统一，V坐标不变"),
        ],
        default='VERTICAL',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            self.report({'WARNING'}, "当前物体没有UV层")
            return {'CANCELLED'}

        # --- UV节点表 ---
        node_pos = {}          # 节点id -> (u, v)
        node_key_map = {}      # (round(u,6), round(v,6)) -> 节点id
        loop_node = {}         # loop -> 节点id

        def get_node(u, v):
            key = (round(u, 6), round(v, 6))
            if key not in node_key_map:
                nid = len(node_pos)
                node_key_map[key] = nid
                node_pos[nid] = (u, v)
            return node_key_map[key]

        # --- 收集选中UV边（跳过隐藏面）---
        # 优先使用UV边选择状态（边模式，精确到每条边），回退到顶点选择（顶点模式）
        edges = set()
        for f in bm.faces:
            if f.hide:
                continue
            for l in f.loops:
                if uv_edge_selected(l, uv_layer):
                    ln = l.link_loop_next
                    a = get_node(l[uv_layer].uv.x, l[uv_layer].uv.y)
                    b = get_node(ln[uv_layer].uv.x, ln[uv_layer].uv.y)
                    if a != b:
                        edges.add((min(a, b), max(a, b)))
                    loop_node[l] = a
                    loop_node[ln] = b

        if not edges:
            # 回退到顶点选择模式
            sel_loops = []
            for f in bm.faces:
                if f.hide:
                    continue
                for l in f.loops:
                    if uv_vert_selected(l, uv_layer):
                        sel_loops.append(l)
            if not sel_loops and context.scene.tool_settings.use_uv_select_sync:
                for f in bm.faces:
                    if f.hide:
                        continue
                    for l in f.loops:
                        if l.vert.select:
                            sel_loops.append(l)
            if not sel_loops:
                self.report({'WARNING'}, "请在UV编辑器中选择一串UV边")
                return {'CANCELLED'}

            for l in sel_loops:
                loop_node[l] = get_node(l[uv_layer].uv.x, l[uv_layer].uv.y)

            for l in sel_loops:
                ln = l.link_loop_next
                if ln in loop_node:
                    a, b = loop_node[l], loop_node[ln]
                    edges.add((min(a, b), max(a, b)))

        if not edges:
            self.report({'WARNING'}, "选中的UV顶点之间没有相连的边")
            return {'CANCELLED'}

        # sel_loops 用于后续钉固和写回UV
        sel_loops = list(loop_node.keys())

        # --- 检查是否为单向相连的开放边链（单一连通、无分支、无闭合环） ---
        chain_nodes = set()
        for a, b in edges:
            chain_nodes.add(a)
            chain_nodes.add(b)
        if len(chain_nodes) != len(node_pos):
            self.report({'WARNING'}, "选中的UV包含未相连的顶点，请只选中一条边链")
            return {'CANCELLED'}

        adj = {nid: [] for nid in chain_nodes}
        for a, b in edges:
            adj[a].append(b)
            adj[b].append(a)
        if any(len(adj[n]) > 2 for n in adj):
            self.report({'WARNING'}, "选中的UV边存在分叉，不是单向相连的边链")
            return {'CANCELLED'}

        endpoints = [n for n in adj if len(adj[n]) == 1]
        if len(endpoints) != 2:
            self.report({'WARNING'}, "选中的UV边链是闭合环，请选择一条开放的边链")
            return {'CANCELLED'}

        # 连通性：从一端出发必须能走完整条链
        seen = set()
        stack = [endpoints[0]]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adj[cur])
        if len(seen) != len(chain_nodes):
            self.report({'WARNING'}, "选中的UV边链不连续，请只选中一条边链")
            return {'CANCELLED'}

        # --- 沿链从一端走到另一端，得到链顺序与累计距离 ---
        order = []
        cur, prev = endpoints[0], -1
        while True:
            order.append(cur)
            nxt = [n for n in adj[cur] if n != prev]
            if not nxt:
                break
            cur, prev = nxt[0], cur

        cumdist = {order[0]: 0.0}
        for i in range(1, len(order)):
            a, b = order[i - 1], order[i]
            ua, va = node_pos[a]
            ub, vb = node_pos[b]
            cumdist[b] = cumdist[a] + math.hypot(ub - ua, vb - va)

        # --- 位置计算 ---
        if self.direction == 'VERTICAL':
            # 拉直：最上方点为锚点，其余点沿垂直线向下排布，距离保持
            anchor = max(chain_nodes, key=lambda n: node_pos[n][1])
            ax, ay = node_pos[anchor]
            new_pos = {nid: (ax, ay - abs(cumdist[nid] - cumdist[anchor]))
                       for nid in chain_nodes}
        elif self.direction == 'HORIZONTAL':
            # 拉直：最左边点为锚点，其余点沿水平线向右排布，距离保持
            anchor = min(chain_nodes, key=lambda n: node_pos[n][0])
            ax, ay = node_pos[anchor]
            new_pos = {nid: (ax + abs(cumdist[nid] - cumdist[anchor]), ay)
                       for nid in chain_nodes}
        elif self.direction == 'ALIGN_VERTICAL':
            # 对齐：所有点的U坐标统一为锚点U，V坐标不变
            anchor = max(chain_nodes, key=lambda n: node_pos[n][1])
            ax = node_pos[anchor][0]
            new_pos = {nid: (ax, node_pos[nid][1]) for nid in chain_nodes}
        else:  # ALIGN_HORIZONTAL
            # 对齐：所有点的V坐标统一为锚点V，U坐标不变
            anchor = min(chain_nodes, key=lambda n: node_pos[n][0])
            ay = node_pos[anchor][1]
            new_pos = {nid: (node_pos[nid][0], ay) for nid in chain_nodes}

        # --- 开启实时展开 ---
        space = context.space_data
        if space and hasattr(space, 'uv_editor') and hasattr(space.uv_editor, 'use_live_unwrap'):
            space.uv_editor.use_live_unwrap = True

        # --- 钉固选中顶点（作为 Live Unwrap 的约束） ---
        for l in sel_loops:
            uv_vert_pin_set(l, uv_layer, True)

        # --- 写回UV坐标（拉直） ---
        for l in sel_loops:
            l[uv_layer].uv = new_pos[loop_node[l]]

        bmesh.update_edit_mesh(obj.data)

        # --- 原地设置位置触发实时展开 ---
        # Live Unwrap 已开启，通过零位移 translate 触发未钉固部分根据钉固顶点重新展开
        bpy.ops.transform.translate(value=(0, 0, 0))

        dir_text = {'VERTICAL': '垂直拉直', 'HORIZONTAL': '水平拉直',
                    'ALIGN_VERTICAL': '垂直对齐', 'ALIGN_HORIZONTAL': '水平对齐'}[self.direction]
        self.report({'INFO'}, f"UV边链拉直完成: {len(chain_nodes)}个顶点({dir_text}), 已钉固并触发实时展开")
        return {'FINISHED'}


classes = (
    XQFA_PT_UVMiscTools,
    XQFA_OT_GravityUV,
    XQFA_OT_StraightenUVChain,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
