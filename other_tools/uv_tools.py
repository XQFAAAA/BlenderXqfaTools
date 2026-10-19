# type: ignore
import colorsys
import json
import math
import os
import random

import bmesh
import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader


# ---------------------------------------------------------------------------
# 兼容 Blender 4.x / 5.x 的 UV 顶点选择读取
# 5.0+ 移除了 BMLoopUV.select，改用 BMLoop.uv_select_vert
# ---------------------------------------------------------------------------

def _uv_vert_selected(loop, uv_layer):
    """读取某个 loop 对应的 UV 顶点是否被选中"""
    if hasattr(loop, 'uv_select_vert'):
        return loop.uv_select_vert
    return loop[uv_layer].select


# ---------------------------------------------------------------------------
# 数据模型：吸附点保存在场景中（随 .blend 保存），全局可用
# 同一文件内的任意物体、任意 UV 贴图都能使用这些吸附点
# ---------------------------------------------------------------------------

_PALETTE_HUE_GAP = 0.12


def _largest_gap_hue(existing_hues):
    """在已有色相的最大空隙中间取一个新色相（带随机抖动）

    色相空间放不下更多间隔时用它兜底，保证层数再多也尽量分散。
    """
    if not existing_hues:
        return random.random()

    hues = sorted(existing_hues)
    best_gap = -1.0
    best_start = 0.0
    for i, start in enumerate(hues):
        end = hues[(i + 1) % len(hues)]
        gap = (end - start) % 1.0
        if gap > best_gap:
            best_gap, best_start = gap, start

    # 落在最大空隙的中间一半，避免贴近两侧已有色相
    jitter = random.uniform(0.25, 0.75) * best_gap
    return (best_start + jitter) % 1.0


def _random_distinct_color(existing_colors):
    """生成一个与新层「随机但能分辨」的颜色（RGBA）

    在 HSV 空间随机取色（高饱和、高亮度，避免灰暗难辨），并保证与已有
    层颜色的色相环形距离不小于 _PALETTE_HUE_GAP；色相空间被占满（层数
    较多）时退回最大空隙填充，让色相始终尽量均匀分散。
    """
    existing_hues = [
        colorsys.rgb_to_hsv(c[0], c[1], c[2])[0] for c in existing_colors
    ]

    def _far_enough(hue):
        return all(
            min(abs(hue - h), 1.0 - abs(hue - h)) >= _PALETTE_HUE_GAP
            for h in existing_hues
        )

    hue = random.random()
    for _ in range(24):
        if _far_enough(hue):
            break
        hue = random.random()
    else:
        hue = _largest_gap_hue(existing_hues)

    sat = random.uniform(0.65, 1.0)
    val = random.uniform(0.85, 1.0)
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return (r, g, b, 1.0)


class XQFA_UVSnapPoint(bpy.types.PropertyGroup):
    u: bpy.props.FloatProperty(name="U", default=0.0)
    v: bpy.props.FloatProperty(name="V", default=0.0)


class XQFA_UVSnapLayer(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="层名", default="吸附层")
    color: bpy.props.FloatVectorProperty(
        name="颜色", subtype='COLOR_GAMMA', size=4,
        default=(1.0, 0.5, 0.0, 1.0), min=0.0, max=1.0,
    )
    enabled: bpy.props.BoolProperty(
        name="启用", description="是否高亮显示并参与吸附", default=True,
    )
    points: bpy.props.CollectionProperty(type=XQFA_UVSnapPoint)


def _active_layer(scene, create_if_missing=False):
    """返回当前激活吸附层，索引越界时可选自动新建"""
    layers = scene.xqfa_uv_snap_layers
    idx = scene.xqfa_uv_snap_active_layer
    if 0 <= idx < len(layers):
        return layers[idx]
    if create_if_missing:
        existing_colors = [tuple(l.color) for l in layers]
        layer = layers.add()
        layer.name = f"吸附层 {len(layers)}"
        layer.color = _random_distinct_color(existing_colors)
        scene.xqfa_uv_snap_active_layer = len(layers) - 1
        return layer
    return None


def _add_point(layer, u, v, tol=1e-6):
    """向层中添加吸附点，重复位置返回 False"""
    for p in layer.points:
        if abs(p.u - u) <= tol and abs(p.v - v) <= tol:
            return False
    p = layer.points.add()
    p.u = u
    p.v = v
    return True


def _has_enabled_points(scene):
    """是否存在可参与吸附的吸附点（用于 poll 判断是否接管 G 键）"""
    for layer in scene.xqfa_uv_snap_layers:
        if layer.enabled and len(layer.points):
            return True
    return False


def _enabled_targets(scene):
    """所有启用层里的吸附点坐标"""
    return [
        (p.u, p.v)
        for layer in scene.xqfa_uv_snap_layers if layer.enabled
        for p in layer.points
    ]


def _selected_node_loops(bm, uv_layer, sync):
    """收集选中 UV 点，按 UV 坐标去重后返回 {坐标: [loop,...]}"""
    nodes = {}
    for f in bm.faces:
        if f.hide:
            continue
        for l in f.loops:
            if sync:
                if not l.vert.select:
                    continue
            elif not _uv_vert_selected(l, uv_layer):
                continue
            uv = l[uv_layer].uv
            key = (round(uv.x, 6), round(uv.y, 6))
            nodes.setdefault(key, []).append(l)
    return nodes


def _collect_selected_uv(bm, uv_layer, sync):
    """收集选中的 UV 点坐标（按 UV 坐标去重）"""
    return list(_selected_node_loops(bm, uv_layer, sync).keys())


def _loop_uv_records(bm, uv_layer, sync=None):
    """按 (面序号, 环序号) 记录 UV 坐标。

    - sync 为 True / False：只记录选中的 loop（分别是顶点选择 / UV 选择）
    - sync 为 None：记录全部 loop（用于取消时还原快照）

    面序号与环序号在 modal 期间保持稳定（拓扑不变），
    因此可以跨帧用 bm.faces[面序号] 重新定位 loop；
    BMLoop 引用在每次 update_edit_mesh 后失效，绝不能跨帧缓存。
    """
    records = []
    for fi, f in enumerate(bm.faces):
        if f.hide and sync is not None:
            continue
        for li, l in enumerate(f.loops):
            if sync is not None:
                if sync:
                    if not l.vert.select:
                        continue
                elif not _uv_vert_selected(l, uv_layer):
                    continue
            uv = l[uv_layer].uv
            records.append((fi, li, uv.x, uv.y))
    return records


# ---------------------------------------------------------------------------
# 实时展开相关的读取
# ---------------------------------------------------------------------------

def _has_live_unwrap_pins(bm, uv_layer):
    """是否存在足以驱动“实时展开”的固定点（pin）

    Blender 手册明确说明：实时展开需要“固定两个及以上 UV”才会起作用
    （见 4.5 / 5.2 手册 UV 编辑页的 Pinning 段落：
    “If you pin two or more UVs, with Live Unwrap on, moving or scaling the
    pinned UVs will interactively unwrap the model.”）。
    只有 1 个固定点时展开求解是欠定的（旋转/缩放自由），会来回漂移；
    而一个固定点都没有时，解算会把整块 UV 从零重算、丢失手动布局。
    因此这里统计被固定的不同 UV 顶点数，达到 2 个才返回 True。
    """
    pinned = set()
    for f in bm.faces:
        if f.hide:
            continue
        for l in f.loops:
            if getattr(l[uv_layer], 'pin_uv', False):
                uv = l[uv_layer].uv
                pinned.add((round(uv.x, 6), round(uv.y, 6)))
                if len(pinned) >= 2:
                    return True
    return False


def _uv_scale_per_pixel(view2d):
    """1 像素对应的 (U, V) 距离，用于像素与 UV 距离的换算"""
    p0 = view2d.region_to_view(0.0, 0.0)
    p1 = view2d.region_to_view(1.0, 0.0)
    p2 = view2d.region_to_view(0.0, 1.0)
    if p0 is None or p1 is None or p2 is None:
        return (1e-4, 1e-4)
    return (max(abs(p1[0] - p0[0]), 1e-9), max(abs(p2[1] - p0[1]), 1e-9))


def _window_region(area):
    """取区域的 WINDOW 子区域（面板按钮触发时 context.region 是 UI 区域）"""
    if area is None:
        return None
    for region in area.regions:
        if region.type == 'WINDOW':
            return region
    return None


# ---------------------------------------------------------------------------
# 吸附层管理
# ---------------------------------------------------------------------------

class XQFA_OT_UVSnapAddLayer(bpy.types.Operator):
    """新建一个吸附层，用于分层管理吸附点"""
    bl_idname = "xqfa.uv_snap_add_layer"
    bl_label = "新建吸附层"
    bl_description = "新建一个吸附层，用于分层管理吸附点"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        layers = scene.xqfa_uv_snap_layers
        existing_colors = [tuple(l.color) for l in layers]
        layer = layers.add()
        layer.name = f"吸附层 {len(layers)}"
        layer.color = _random_distinct_color(existing_colors)
        scene.xqfa_uv_snap_active_layer = len(layers) - 1
        return {'FINISHED'}


class XQFA_OT_UVSnapRemoveLayer(bpy.types.Operator):
    """删除当前吸附层及其所有吸附点"""
    bl_idname = "xqfa.uv_snap_remove_layer"
    bl_label = "删除吸附层"
    bl_description = "删除当前吸附层及其所有吸附点"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        layers = scene.xqfa_uv_snap_layers
        idx = scene.xqfa_uv_snap_active_layer
        if not (0 <= idx < len(layers)):
            self.report({'WARNING'}, "没有可删除的吸附层")
            return {'CANCELLED'}
        name = layers[idx].name
        layers.remove(idx)
        scene.xqfa_uv_snap_active_layer = max(0, min(idx, len(layers) - 1))
        self.report({'INFO'}, f"已删除吸附层“{name}”")
        return {'FINISHED'}


class XQFA_OT_UVSnapClearLayer(bpy.types.Operator):
    """删除当前吸附层中的所有吸附点（保留层）"""
    bl_idname = "xqfa.uv_snap_clear_layer"
    bl_label = "清空当前层"
    bl_description = "删除当前吸附层中的所有吸附点（保留层）"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        layer = _active_layer(context.scene)
        if layer is None:
            self.report({'WARNING'}, "没有可清空的吸附层")
            return {'CANCELLED'}
        count = len(layer.points)
        layer.points.clear()
        self.report({'INFO'}, f"已清空 {count} 个吸附点")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# 添加吸附点
# ---------------------------------------------------------------------------

class XQFA_OT_UVSnapAddSelected(bpy.types.Operator):
    """把 UV 编辑器中选中的 UV 点位置添加为当前层的吸附点"""
    bl_idname = "xqfa.uv_snap_add_selected"
    bl_label = "从选中UV点添加"
    bl_description = "把 UV 编辑器中选中的 UV 点位置添加为当前层的吸附点"
    bl_options = {'REGISTER', 'UNDO'}

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

        sync = context.scene.tool_settings.use_uv_select_sync
        coords = _collect_selected_uv(bm, uv_layer, sync)
        if not coords:
            self.report({'WARNING'}, "没有选中的UV点")
            return {'CANCELLED'}

        layer = _active_layer(context.scene, create_if_missing=True)
        added = sum(1 for (u, v) in coords if _add_point(layer, u, v))
        self.report({'INFO'}, f"已添加 {added} 个吸附点（选中 {len(coords)} 个）")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# 预设：保存 / 加载吸附层（文件存放在插件目录下的 uv_snap_presets 文件夹）
# ---------------------------------------------------------------------------

_PRESET_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "uv_snap_presets"
)
_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def _ensure_preset_dir():
    os.makedirs(_PRESET_DIR, exist_ok=True)


def _safe_preset_name(name):
    """把用户输入的名称转成安全的文件名（去掉非法字符）"""
    cleaned = "".join(c for c in name if c not in _INVALID_FILENAME_CHARS).strip()
    return cleaned or "预设"


def _list_preset_files():
    """预设目录下所有 .json 预设文件名（已排序），目录不存在时返回空"""
    try:
        files = os.listdir(_PRESET_DIR)
    except OSError:
        return []
    return sorted(f for f in files if f.lower().endswith(".json"))


def _preset_enum_items(self, context):
    return [(f, os.path.splitext(f)[0], "") for f in _list_preset_files()]


def _serialize_layers(scene):
    return [
        {
            "name": layer.name,
            "color": list(layer.color),
            "enabled": layer.enabled,
            "points": [[p.u, p.v] for p in layer.points],
        }
        for layer in scene.xqfa_uv_snap_layers
    ]


def _apply_layers(scene, layers_data):
    """用预设数据整体替换场景里的吸附层"""
    layers = scene.xqfa_uv_snap_layers
    for i in range(len(layers) - 1, -1, -1):
        layers.remove(i)
    for data in layers_data:
        layer = layers.add()
        layer.name = data.get("name") or "吸附层"
        color = data.get("color") or (1.0, 0.5, 0.0, 1.0)
        layer.color = tuple(float(c) for c in color)
        layer.enabled = bool(data.get("enabled", True))
        for u, v in data.get("points", []):
            p = layer.points.add()
            p.u = float(u)
            p.v = float(v)
    scene.xqfa_uv_snap_active_layer = len(layers) - 1 if len(layers) else 0


class XQFA_OT_UVSnapSavePreset(bpy.types.Operator):
    """把当前所有吸附层保存为插件目录下的预设文件"""
    bl_idname = "xqfa.uv_snap_save_preset"
    bl_label = "保存预设"
    bl_description = "把当前所有吸附层保存到插件目录（uv_snap_presets）"
    bl_options = {'REGISTER'}

    preset_name: bpy.props.StringProperty(name="预设名", default="预设")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=240)

    def execute(self, context):
        name = _safe_preset_name(self.preset_name)
        try:
            _ensure_preset_dir()
            path = os.path.join(_PRESET_DIR, f"{name}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"layers": _serialize_layers(context.scene)}, f,
                          ensure_ascii=False, indent=2)
        except OSError as e:
            self.report({'ERROR'}, f"保存预设失败：{e}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"已保存预设「{name}」")
        return {'FINISHED'}


class XQFA_OT_UVSnapLoadPreset(bpy.types.Operator):
    """从插件目录加载预设，替换当前所有吸附层"""
    bl_idname = "xqfa.uv_snap_load_preset"
    bl_label = "加载预设"
    bl_description = "从插件目录加载预设，替换当前所有吸附层"
    bl_options = {'REGISTER', 'UNDO'}

    preset: bpy.props.EnumProperty(name="预设", items=_preset_enum_items)

    def invoke(self, context, event):
        if not _list_preset_files():
            self.report({'WARNING'}, "插件目录下没有任何预设")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=240)

    def execute(self, context):
        path = os.path.join(_PRESET_DIR, self.preset)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _apply_layers(context.scene, data.get("layers", []))
        except (OSError, ValueError, TypeError) as e:
            self.report({'ERROR'}, f"读取预设失败：{e}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"已加载预设「{os.path.splitext(self.preset)[0]}」")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# 吸附移动（自建 modal）
#
# 为什么必须自建 modal：原生 UV Transform 每一帧都用“初始坐标 + 鼠标位移”
# 绝对重算 UV，任何外部写入下一帧就被覆盖，无法从外部注入吸附；
# 而“实时展开”的解算器只活在原生 transform 内部（C 层），Python 无入口。
# 所以这里接管 G 键，自己完成“移动 + 吸附”，并在确认吸附后触发一次实时展开：
# 先临时关闭「启用吸附」→ 执行一次原生 0 单位移动 → 再恢复开关；
# 若该原生调用没有产生解算（0 位移本身不会移动任何点，只能靠解算器产生变化），
# 再退回调用原生解算器 bpy.ops.uv.unwrap()，保证展开一定发生。
#
# 坐标来源使用 event.mouse_x / mouse_y（屏幕坐标，与触发区域无关），
# 因此无论从 G 键还是面板按钮触发都能正确工作。
# ---------------------------------------------------------------------------


class XQFA_OT_UVSnapMove(bpy.types.Operator):
    """吸附移动：在 UV 编辑器里移动选中的 UV 点，自动磁吸到最近的吸附点"""
    bl_idname = "xqfa.uv_snap_move"
    bl_label = "UV 吸附移动"
    bl_description = ("移动选中的 UV 点，并在吸附距离内磁吸到最近的吸附点；"
                      "开启实时展开且固定了 2 个以上点时，确认吸附后重算展开")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        area = getattr(context, 'area', None)
        if area is None or area.type != 'IMAGE_EDITOR':
            return False
        scene = getattr(context, 'scene', None)
        if scene is None or not scene.xqfa_uv_snap_enabled:
            return False
        if not _has_enabled_points(scene):
            return False
        obj = getattr(context, 'edit_object', None)
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    # -- 生命周期 ---------------------------------------------------------

    def invoke(self, context, event):
        self.area = context.area
        self.window = context.window
        self.scene = context.scene
        self.view_layer = context.view_layer
        self.region = _window_region(self.area)
        self.obj = context.edit_object
        if self.obj is None or self.region is None:
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(self.obj.data)
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            self.report({'WARNING'}, "当前物体没有UV层")
            return {'CANCELLED'}

        self.sync = context.scene.tool_settings.use_uv_select_sync
        self.selection = _loop_uv_records(bm, uv_layer, self.sync)
        if not self.selection:
            self.report({'WARNING'}, "没有选中的UV点")
            return {'CANCELLED'}
        # 取消时用整网格快照还原（实时展开会把未固定的 UV 一起改动）
        self.snapshot = _loop_uv_records(bm, uv_layer, None)

        self.live_unwrap = bool(
            getattr(getattr(context.space_data, 'uv_editor', None),
                    'use_live_unwrap', False))
        self.axis = None          # 轴向锁定：None / 'X'(U) / 'Y'(V)
        self.armed = False        # 首次鼠标移动时重新锚定，避免起点跳变
        self.mouse_start = (event.mouse_x, event.mouse_y)

        context.window_manager.modal_handler_add(self)
        self._apply(context, self.mouse_start)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in ('MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'):
            mouse = (event.mouse_x, event.mouse_y)
            if not self.armed:
                self.armed = True
                self.mouse_start = mouse
            self._apply(context, mouse)
            return {'RUNNING_MODAL'}

        if event.type in ('LEFTMOUSE', 'RETURN', 'SPACE') and event.value == 'PRESS':
            self._finish_unwrap(context)
            return {'FINISHED'}

        if event.type in ('RIGHTMOUSE', 'ESC'):
            self._restore()
            return {'CANCELLED'}

        if event.type in ('X', 'Y') and event.value == 'PRESS':
            self.axis = None if self.axis == event.type else event.type
            self._apply(context, (event.mouse_x, event.mouse_y))
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    # -- 内部实现 ---------------------------------------------------------

    def _apply(self, context, mouse):
        obj = self.obj
        if obj is None or obj.mode != 'EDIT':
            return

        dx = mouse[0] - self.mouse_start[0]
        dy = mouse[1] - self.mouse_start[1]
        if self.axis == 'X':
            dy = 0.0
        elif self.axis == 'Y':
            dx = 0.0

        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            return

        sx, sy = _uv_scale_per_pixel(self.region.view2d)
        sx = max(sx, 1e-9)
        sy = max(sy, 1e-9)

        # 1) 由「初始坐标 + 鼠标位移」重算临时位置（绝对重算，不累积误差）
        tmp = [(iu + dx * sx, iv + dy * sy) for (_fi, _li, iu, iv) in self.selection]

        # 2) 磁吸：在「所有选中点 × 所有吸附点」中找像素距离最近的一对
        targets = _enabled_targets(self.scene)
        off_u = off_v = 0.0
        best = None
        for (u, v) in tmp:
            for (tu, tv) in targets:
                ddx = (tu - u) / sx
                ddy = (tv - v) / sy
                d2 = ddx * ddx + ddy * ddy
                if best is None or d2 < best[0]:
                    best = (d2, tu - u, tv - v)
        thr = self.scene.xqfa_uv_snap_distance
        if best is not None and best[0] <= thr * thr:
            off_u = best[1]
            off_v = best[2]

        # 3) 写回选中 UV 点
        face_count = len(bm.faces)
        for (fi, li, _iu, _iv), (u, v) in zip(self.selection, tmp):
            if fi >= face_count:
                continue
            for k, l in enumerate(bm.faces[fi].loops):
                if k == li:
                    luv = l[uv_layer].uv
                    luv.x = u + off_u
                    luv.y = v + off_v
                    break

        # 4) 写回并刷新（实时展开在确认吸附时统一解算，见 _finish_unwrap）
        bmesh.update_edit_mesh(obj.data)
        if self.area is not None:
            self.area.tag_redraw()

    def _finish_unwrap(self, context):
        """确认吸附后触发一次实时展开

        做法：临时关闭「启用吸附」→ 执行一次原生 0 单位移动 → 恢复开关。
        0 位移本身不会移动任何 UV，只能靠原生 transform 内部的实时展开
        解算器产生变化；若这次原生调用没能改变 UV，再退回调用原生解算器
        bpy.ops.uv.unwrap()，确保展开一定发生。

        仅在 UV 编辑器开启实时展开、且固定点 ≥2 时执行
        （与 Blender 手册的实时展开前提一致：固定两个及以上 UV 才有意义）。
        """
        if not self.live_unwrap:
            return
        obj = self.obj
        if obj is None or obj.mode != 'EDIT':
            return
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None or not _has_live_unwrap_pins(bm, uv_layer):
            return

        before = _loop_uv_records(bm, uv_layer, None)

        # 1) 临时关闭「启用吸附」，让后续走原生路径
        scene = self.scene
        was_enabled = scene.xqfa_uv_snap_enabled
        scene.xqfa_uv_snap_enabled = False

        # 2) 原生移动 0 个单位
        resolved = False
        try:
            with context.temp_override(
                window=self.window, area=self.area, region=self.region,
                scene=self.scene, view_layer=self.view_layer,
            ):
                result = bpy.ops.transform.translate(value=(0.0, 0.0, 0.0))
            resolved = 'FINISHED' in result
        except Exception:
            resolved = False
        finally:
            # 3) 恢复「启用吸附」
            scene.xqfa_uv_snap_enabled = was_enabled

        # 位移为 0 时 UV 只会因解算器而改变，据此判断原生解算是否真的跑了
        if resolved:
            bm2 = bmesh.from_edit_mesh(obj.data)
            uv2 = bm2.loops.layers.uv.active
            resolved = uv2 is not None and _loop_uv_records(bm2, uv2, None) != before

        if not resolved:
            self._run_unwrap(context)

    def _run_unwrap(self, context):
        """在正确的上下文里调用 UV 编辑器的「实时展开」解算器"""
        try:
            with context.temp_override(
                window=self.window,
                area=self.area,
                region=self.region,
                scene=self.scene,
                view_layer=self.view_layer,
            ):
                bpy.ops.uv.unwrap()
        except Exception:
            pass

    def _restore(self):
        """取消：还原整网格 UV 到进入 modal 时的状态"""
        obj = self.obj
        if obj is None:
            return
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is not None:
            face_count = len(bm.faces)
            for (fi, li, iu, iv) in self.snapshot:
                if fi >= face_count:
                    continue
                for k, l in enumerate(bm.faces[fi].loops):
                    if k == li:
                        luv = l[uv_layer].uv
                        luv.x = iu
                        luv.y = iv
                        break
        bmesh.update_edit_mesh(obj.data)
        if self.area is not None:
            self.area.tag_redraw()


# ---------------------------------------------------------------------------
# 吸附点高亮叠加显示（在 UV 编辑器中绘制）
# ---------------------------------------------------------------------------

_draw_handle = None


def _append_circle(coords, indices, cx, cy, radius, segments=14):
    """向顶点/索引列表追加一个实心圆（三角扇形）"""
    base = len(coords)
    coords.append((cx, cy))
    for i in range(segments):
        ang = (2.0 * math.pi * i) / segments
        coords.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
    for i in range(segments):
        nxt = (i + 1) % segments
        indices.append((base, base + 1 + i, base + 1 + nxt))


def _draw_uv_snap_overlay():
    context = bpy.context
    scene = getattr(context, 'scene', None)
    region = getattr(context, 'region', None)
    space = getattr(context, 'space_data', None)
    view2d = getattr(region, 'view2d', None)

    if scene is None or not scene.xqfa_uv_snap_show_overlay:
        return

    layers = scene.xqfa_uv_snap_layers
    if not len(layers):
        return

    if region is None or space is None or getattr(space, 'type', '') != 'IMAGE_EDITOR':
        return
    if getattr(space, 'mode', 'UV') != 'UV':
        return

    if view2d is None:
        return

    radius = scene.xqfa_uv_snap_marker_size
    show_names = scene.xqfa_uv_snap_show_names

    gpu.state.blend_set('ALPHA')
    try:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        for layer in layers:
            if not layer.enabled or not len(layer.points):
                continue

            coords = []
            indices = []
            labels = []
            for p in layer.points:
                pos = view2d.view_to_region(p.u, p.v, clip=False)
                if pos is None:
                    continue
                px, py = pos[0], pos[1]
                _append_circle(coords, indices, px, py, radius)
                if show_names:
                    labels.append((px, py))

            if indices:
                batch = batch_for_shader(shader, 'TRIS', {"pos": coords}, indices=indices)
                shader.uniform_float("color", tuple(layer.color))
                batch.draw(shader)

            if labels:
                font_id = 0
                blf.size(font_id, 14)
                blf.color(font_id, layer.color[0], layer.color[1], layer.color[2], 1.0)
                off = radius + 3.0
                for px, py in labels:
                    blf.position(font_id, px + off, py - 5.0, 0)
                    blf.draw(font_id, layer.name)
    finally:
        gpu.state.blend_set('NONE')


# ---------------------------------------------------------------------------
# 界面
# ---------------------------------------------------------------------------

class XQFA_UL_UVSnapLayers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.prop(item, "color", text="")
        row.prop(item, "name", text="", emboss=False)
        row.label(text=str(len(item.points)))


class XQFA_PT_UVSnapPoints(bpy.types.Panel):
    bl_label = "UV 吸附点"
    bl_idname = "XQFA_PT_uv_snap_points"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "xqfa_uv_snap_show_overlay", text="高亮显示吸附点")
        row = col.row(align=True)
        row.prop(scene, "xqfa_uv_snap_show_names", text="显示层名")
        row.prop(scene, "xqfa_uv_snap_marker_size", text="大小")

        row = layout.row(align=True)
        row.prop(
            scene, "xqfa_uv_snap_enabled",
            text="启用吸附", toggle=True, icon='SNAP_ON',
        )
        row.prop(scene, "xqfa_uv_snap_distance", text="距离")

        row = layout.row()
        row.template_list(
            "XQFA_UL_UVSnapLayers", "",
            scene, "xqfa_uv_snap_layers",
            scene, "xqfa_uv_snap_active_layer",
            rows=4,
        )
        col2 = row.column(align=True)
        col2.operator(XQFA_OT_UVSnapAddLayer.bl_idname, icon='ADD', text="")
        col2.operator(XQFA_OT_UVSnapRemoveLayer.bl_idname, icon='REMOVE', text="")
        col2.separator()
        col2.operator(XQFA_OT_UVSnapLoadPreset.bl_idname, icon='IMPORT', text="")
        col2.operator(XQFA_OT_UVSnapSavePreset.bl_idname, icon='EXPORT', text="")

        row = layout.row(align=True)
        row.operator(XQFA_OT_UVSnapAddSelected.bl_idname, text="指定")
        row.operator(XQFA_OT_UVSnapClearLayer.bl_idname, text="清空")


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------

classes = (
    XQFA_UVSnapPoint,
    XQFA_UVSnapLayer,
    XQFA_OT_UVSnapAddLayer,
    XQFA_OT_UVSnapRemoveLayer,
    XQFA_OT_UVSnapClearLayer,
    XQFA_OT_UVSnapAddSelected,
    XQFA_OT_UVSnapSavePreset,
    XQFA_OT_UVSnapLoadPreset,
    XQFA_OT_UVSnapMove,
    XQFA_UL_UVSnapLayers,
    XQFA_PT_UVSnapPoints,
)

_addon_keymaps = []


def _register_keymaps():
    """把「吸附移动」绑到 UV 编辑器的 G 键

    UV 编辑器的原生键位表本身 space_type 就是 EMPTY，必须保持一致，
    否则会创建一个永远不会被查询到的孤儿键位表。
    本操作符的 poll 会在「未开启吸附 / 没有吸附点 / 非编辑模式」时返回 False，
    此时 Blender 会继续匹配下一个键位项，即原生 transform.translate。
    """
    wm = getattr(bpy.context, 'window_manager', None)
    if wm is None:
        return
    kc = getattr(wm, 'keyconfigs', None)
    addon_kc = getattr(kc, 'addon', None) if kc is not None else None
    if addon_kc is None:
        return
    km = addon_kc.keymaps.new(name='UV Editor', space_type='EMPTY')
    kmi = km.keymap_items.new(XQFA_OT_UVSnapMove.bl_idname, 'G', 'PRESS')
    _addon_keymaps.append((km, kmi))


def _unregister_keymaps():
    for km, kmi in _addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _addon_keymaps.clear()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # 场景级属性：数据随 .blend 保存，同一文件内所有物体/UV 共享
    bpy.types.Scene.xqfa_uv_snap_layers = bpy.props.CollectionProperty(type=XQFA_UVSnapLayer)
    bpy.types.Scene.xqfa_uv_snap_active_layer = bpy.props.IntProperty(default=0)
    bpy.types.Scene.xqfa_uv_snap_show_overlay = bpy.props.BoolProperty(
        name="高亮显示吸附点", default=True,
    )
    bpy.types.Scene.xqfa_uv_snap_show_names = bpy.props.BoolProperty(
        name="显示层名", default=True,
    )
    bpy.types.Scene.xqfa_uv_snap_marker_size = bpy.props.FloatProperty(
        name="标记大小", default=6.0, min=2.0, max=30.0,
    )
    bpy.types.Scene.xqfa_uv_snap_enabled = bpy.props.BoolProperty(
        name="启用吸附",
        description="开启后，UV 编辑器中的 G 键为吸附移动；关闭时回退为原生移动",
        default=False,
    )
    bpy.types.Scene.xqfa_uv_snap_distance = bpy.props.FloatProperty(
        name="吸附距离",
        description="移动时距离吸附点多少像素以内即触发吸附",
        default=12.0, min=1.0, max=100.0,
    )

    global _draw_handle
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceImageEditor.draw_handler_add(
            _draw_uv_snap_overlay, (), 'WINDOW', 'POST_PIXEL'
        )

    _register_keymaps()


def unregister():
    global _draw_handle

    _unregister_keymaps()

    if _draw_handle is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    for name in (
        'xqfa_uv_snap_layers',
        'xqfa_uv_snap_active_layer',
        'xqfa_uv_snap_show_overlay',
        'xqfa_uv_snap_show_names',
        'xqfa_uv_snap_marker_size',
        'xqfa_uv_snap_enabled',
        'xqfa_uv_snap_distance',
    ):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
