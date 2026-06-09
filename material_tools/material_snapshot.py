# type: ignore
import bpy


# --- 属性组 ---

class SnapshotLinkItem(bpy.types.PropertyGroup):
    """存储单条连接的信息"""
    from_node: bpy.props.StringProperty()
    from_socket: bpy.props.StringProperty()
    from_socket_index: bpy.props.IntProperty()
    to_node: bpy.props.StringProperty()
    to_socket: bpy.props.StringProperty()
    to_socket_index: bpy.props.IntProperty()
    is_muted: bpy.props.BoolProperty()


class SnapshotNodeItem(bpy.types.PropertyGroup):
    """存储节点静音状态"""
    node_name: bpy.props.StringProperty()
    is_muted: bpy.props.BoolProperty()


class SnapshotMaterialItem(bpy.types.PropertyGroup):
    """存储单个材质的连接快照"""
    material_name: bpy.props.StringProperty()
    links: bpy.props.CollectionProperty(type=SnapshotLinkItem)
    nodes_muted: bpy.props.CollectionProperty(type=SnapshotNodeItem)


class MaterialSnapshotItem(bpy.types.PropertyGroup):
    """存储一个快照（包含多个材质）"""
    name: bpy.props.StringProperty(name="快照名称")
    materials: bpy.props.CollectionProperty(type=SnapshotMaterialItem)


# --- 操作符 ---

class XQFA_OT_take_snapshot(bpy.types.Operator):
    """记录选中物体所有材质的连接状态"""
    bl_idname = "xqfa.take_material_snapshot"
    bl_label = "拍摄快照"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}]
        if not selected:
            self.report({'WARNING'}, "未选中可用的物体")
            return {'CANCELLED'}

        snapshots = context.scene.material_snapshots
        snap = snapshots.add()

        # 生成快照名称
        existing = len(snapshots)
        snap.name = f"快照_{existing}"

        collected_mats = set()
        for obj in selected:
            for slot in obj.material_slots:
                mat = slot.material
                if not mat or not mat.use_nodes or mat.name in collected_mats:
                    continue
                collected_mats.add(mat.name)

                mat_snap = snap.materials.add()
                mat_snap.material_name = mat.name

                for link in mat.node_tree.links:
                    item = mat_snap.links.add()
                    item.from_node = link.from_node.name
                    item.from_socket = link.from_socket.name
                    item.from_socket_index = list(link.from_node.outputs).index(link.from_socket)
                    item.to_node = link.to_node.name
                    item.to_socket = link.to_socket.name
                    item.to_socket_index = list(link.to_node.inputs).index(link.to_socket)
                    item.is_muted = getattr(link, 'is_muted', False)

                for node in mat.node_tree.nodes:
                    n_item = mat_snap.nodes_muted.add()
                    n_item.node_name = node.name
                    n_item.is_muted = node.mute

        if not collected_mats:
            snapshots.remove(len(snapshots) - 1)
            self.report({'WARNING'}, "选中物体没有带节点树的材质")
            return {'CANCELLED'}

        self.report({'INFO'}, f"已拍摄快照: {snap.name}，包含 {len(collected_mats)} 个材质")
        return {'FINISHED'}


class XQFA_OT_apply_snapshot(bpy.types.Operator):
    """恢复选中快照的连接状态"""
    bl_idname = "xqfa.apply_material_snapshot"
    bl_label = "应用快照"
    bl_options = {'REGISTER', 'UNDO'}

    snapshot_name: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        snapshots = scene.material_snapshots
        # 先将选中项移动到点击的项
        idx = next((i for i, s in enumerate(snapshots) if s.name == self.snapshot_name), -1)
        if idx < 0:
            self.report({'ERROR'}, "未找到快照")
            return {'CANCELLED'}
        scene.material_snapshot_index = idx

        snap = snapshots[idx]
        restored = 0
        failed = 0

        for mat_snap in snap.materials:
            mat = bpy.data.materials.get(mat_snap.material_name)
            if not mat or not mat.use_nodes:
                failed += 1
                continue

            nodes = mat.node_tree.nodes
            links = mat.node_tree.links

            # 清除所有现有连接
            for link in list(links):
                links.remove(link)

            # 重建连接
            for link_item in mat_snap.links:
                from_node = nodes.get(link_item.from_node)
                to_node = nodes.get(link_item.to_node)
                if not from_node or not to_node:
                    continue

                # 优先用名称查找，回退用索引
                from_socket = from_node.outputs.get(link_item.from_socket)
                if not from_socket and link_item.from_socket_index < len(from_node.outputs):
                    from_socket = from_node.outputs[link_item.from_socket_index]

                to_socket = to_node.inputs.get(link_item.to_socket)
                if not to_socket and link_item.to_socket_index < len(to_node.inputs):
                    to_socket = to_node.inputs[link_item.to_socket_index]

                if from_socket and to_socket:
                    new_link = links.new(from_socket, to_socket)
                    if hasattr(new_link, 'is_muted'):
                        new_link.is_muted = link_item.is_muted

            # 恢复节点静音状态
            for n_item in mat_snap.nodes_muted:
                node = nodes.get(n_item.node_name)
                if node:
                    node.mute = n_item.is_muted

            restored += 1

        self.report({'INFO'}, f"已应用快照: {snap.name}，恢复 {restored} 个材质" +
                    (f"，{failed} 个材质未找到" if failed else ""))
        return {'FINISHED'}


class XQFA_OT_remove_snapshot(bpy.types.Operator):
    """删除选中的快照"""
    bl_idname = "xqfa.remove_material_snapshot"
    bl_label = "删除快照"
    bl_options = {'REGISTER', 'UNDO'}

    snapshot_name: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        snapshots = scene.material_snapshots
        idx = next((i for i, s in enumerate(snapshots) if s.name == self.snapshot_name), -1)
        if idx < 0:
            return {'CANCELLED'}
        scene.material_snapshot_index = idx
        name = snapshots[idx].name
        snapshots.remove(idx)
        if scene.material_snapshot_index >= len(snapshots):
            scene.material_snapshot_index = max(0, len(snapshots) - 1)
        self.report({'INFO'}, f"已删除快照: {name}")
        return {'FINISHED'}


# --- UI 列表 ---

class XQFA_UL_material_snapshots(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "name", text="", emboss=False, icon='MATERIAL')
        op = row.operator(XQFA_OT_apply_snapshot.bl_idname, text="", icon='PLAY')
        op.snapshot_name = item.name
        op2 = row.operator(XQFA_OT_remove_snapshot.bl_idname, text="", icon='TRASH')
        op2.snapshot_name = item.name


# --- 面板 ---

class XQFA_PT_material_snapshot(bpy.types.Panel):
    bl_label = "材质连接快照"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "XQFA"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row()
        row.template_list(
            "XQFA_UL_material_snapshots", "",
            scene, "material_snapshots",
            scene, "material_snapshot_index",
            rows=5
        )

        col = row.column(align=True)
        col.operator(XQFA_OT_take_snapshot.bl_idname, icon='ADD', text="")
        snap_idx = scene.material_snapshot_index
        if snap_idx < len(scene.material_snapshots):
            col.operator(XQFA_OT_remove_snapshot.bl_idname, icon='REMOVE', text="").snapshot_name = scene.material_snapshots[snap_idx].name

        # 选中快照信息
        if scene.material_snapshots and scene.material_snapshot_index < len(scene.material_snapshots):
            snap = scene.material_snapshots[scene.material_snapshot_index]
            box = layout.box()
            box.label(text=f"材质数: {len(snap.materials)}", icon='MATERIAL')
            total_links = sum(len(m.links) for m in snap.materials)
            box.label(text=f"连接数: {total_links}", icon='LINKED')


# --- 注册 ---

classes = (
    SnapshotLinkItem,
    SnapshotNodeItem,
    SnapshotMaterialItem,
    MaterialSnapshotItem,
    XQFA_OT_take_snapshot,
    XQFA_OT_apply_snapshot,
    XQFA_OT_remove_snapshot,
    XQFA_UL_material_snapshots,
    XQFA_PT_material_snapshot,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.material_snapshots = bpy.props.CollectionProperty(type=MaterialSnapshotItem)
    bpy.types.Scene.material_snapshot_index = bpy.props.IntProperty()


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, 'material_snapshots'):
        del bpy.types.Scene.material_snapshots
    if hasattr(bpy.types.Scene, 'material_snapshot_index'):
        del bpy.types.Scene.material_snapshot_index
