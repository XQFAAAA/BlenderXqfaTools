# type: ignore
import bpy
import numpy as np


class DATA_PT_face_bool_tools(bpy.types.Panel):
    bl_label = "面组"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'AttributeTools'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator(XQFA_OT_MaterialToFaceGroups.bl_idname, icon="FACE_MAPS")
        col.operator(XQFA_OT_FaceGroupsClean.bl_idname, icon="TRASH")


class XQFA_OT_MaterialToFaceGroups(bpy.types.Operator):
    """将选中物体的所有材质转化为同名的面域布尔属性"""
    bl_idname = "xqfa.material_to_face_groups"
    bl_label = "材质-->面组"
    bl_description = "为每个选中物体的每个材质创建同名的布尔型 Face 域属性，材质对应的面设为 True"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and any(
            obj.type == 'MESH' and obj.data.materials for obj in context.selected_objects
        )

    def execute(self, context):
        mesh_objs = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not mesh_objs:
            self.report({'WARNING'}, "未选中任何网格物体")
            return {'CANCELLED'}

        total_created = 0
        processed = 0
        for obj in mesh_objs:
            if not obj.data.materials:
                continue
            mesh = obj.data
            num_faces = len(mesh.polygons)

            for i, mat_slot in enumerate(obj.material_slots):
                mat = mat_slot.material
                name = mat.name if mat else f"Slot_{i}"

                if name in mesh.attributes:
                    mesh.attributes.remove(mesh.attributes[name])

                attr = mesh.attributes.new(name=name, type='BOOLEAN', domain='FACE')
                values = np.zeros(num_faces, dtype=bool)
                values[:] = [poly.material_index == i for poly in mesh.polygons]
                attr.data.foreach_set('value', values)
                total_created += 1
            processed += 1

        self.report({'INFO'}, f"已处理 {processed} 个物体，创建 {total_created} 个面组属性")
        return {'FINISHED'}


class XQFA_OT_FaceGroupsClean(bpy.types.Operator):
    """删除选中物体中所有空的布尔型面域属性"""
    bl_idname = "xqfa.face_groups_clean"
    bl_label = "批量清理面组"
    bl_description = "对选中的所有物体，删除所有值为 False 的布尔型 Face 域属性"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects is not None and any(
            obj.type == 'MESH' for obj in context.selected_objects
        )

    def execute(self, context):
        mesh_objs = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not mesh_objs:
            self.report({'WARNING'}, "未选中任何网格物体")
            return {'CANCELLED'}

        total_removed = 0
        processed = 0
        for obj in mesh_objs:
            mesh = obj.data
            to_remove = []
            for attr in mesh.attributes:
                if attr.domain == 'FACE' and attr.data_type == 'BOOLEAN':
                    data = np.zeros(len(mesh.polygons), dtype=bool)
                    attr.data.foreach_get('value', data)
                    if not data.any():
                        to_remove.append(attr.name)

            for name in reversed(to_remove):
                mesh.attributes.remove(mesh.attributes[name])
                total_removed += 1
            if to_remove:
                processed += 1

        self.report({'INFO'}, f"已清理 {processed} 个物体，删除 {total_removed} 个空面组")
        return {'FINISHED'}


classes = (
    DATA_PT_face_bool_tools,
    XQFA_OT_MaterialToFaceGroups,
    XQFA_OT_FaceGroupsClean,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
