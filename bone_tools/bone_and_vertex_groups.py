# type: ignore
import bpy 
import re
import os
import csv
from bpy_extras.io_utils import ImportHelper
from .bone_pose import _select_pose_bone

########################## Divider ##########################

class ObjType(bpy.types.Operator):
    def is_mesh(scene, obj):
        return obj.type == "MESH"
    
    def is_armature(scene, obj):
        return obj.type == "ARMATURE"


class O_NoVgDelBone(bpy.types.Operator):
    bl_idname = "xqfa.vertex_groups_no_vg_del_bone"
    bl_label = "清理骨骼"
    bl_description = "删除选择的骨骼中无对应顶点组的骨骼"

    def execute(self, context):
        try:
            SourceMesh = bpy.data.objects.get(context.scene.vg_source_mesh.name)
            SourceArmature = bpy.data.objects.get(context.scene.vg_source_armature.name)
        except:
            self.report({'ERROR'}, "似乎没有选择对象") 
            return {'FINISHED'}
        if not context.selected_pose_bones:
            self.report({'ERROR'}, "请进入姿态模式选择骨骼") 
            return {'FINISHED'}
        if SourceArmature != context.active_object:
            self.report({'ERROR'}, "选择的骨架与进入姿态模式的骨架不同") 
            return {'FINISHED'}
        
        del_bones = []
        bpy.ops.object.mode_set(mode='EDIT')
        for bone in context.selected_bones:
            for group in SourceMesh.vertex_groups:
                if bone.name == group.name:
                    break
            else:
                del_bones.append(bone.name)
        
        bpy.ops.armature.select_all(action='DESELECT')
        for bone_name in del_bones:
            bpy.ops.object.select_pattern(pattern=bone_name)
            print(f"已删除{bone_name}骨骼")
        bpy.ops.armature.delete()

        bpy.ops.object.mode_set(mode='POSE')
        self.report({'INFO'}, f"已删除{len(del_bones)}个无对应顶点组的骨骼！")
        return {'FINISHED'}

class O_NoBoneDelVg(bpy.types.Operator):
    bl_idname = "xqfa.vertex_groups_no_bone_del_vg"
    bl_label = "清理顶点组"
    bl_description = "删除顶点组中无对应骨骼的顶点组"
    
    def execute(self, context):
        try:
            SourceMesh = bpy.data.objects.get(context.scene.vg_source_mesh.name)
            SourceArmature = bpy.data.objects.get(context.scene.vg_source_armature.name)
        except:
            self.report({'ERROR'}, "似乎没有选择对象") 
            return {'FINISHED'}
        
        del_groups = []
        for group in SourceMesh.vertex_groups:
            for bone in SourceArmature.data.bones:
                if group.name == bone.name:
                    break
            else:
                del_groups.append(group.name)
                SourceMesh.vertex_groups.remove(group)
        
        for group_name in del_groups:
            print(f"已删除{group_name}顶点组")

        self.report({'INFO'}, f"已删除{len(del_groups)}个无对应骨骼的顶点组！")
        return {'FINISHED'}

########################## Divider ##########################

class O_SelectWeightedBones(bpy.types.Operator):
    bl_idname = "xqfa.vertex_groups_add_bone_number"
    bl_label = "选择有权重骨骼"
    bl_description = "选择绑定到当前网格物体且有权重的骨骼"
    
    def execute(self, context):
        try:
            SourceMesh = bpy.data.objects.get(context.scene.vg_source_mesh.name)
            SourceArmature = bpy.data.objects.get(context.scene.vg_source_armature.name)
        except:
            self.report({'ERROR'}, "似乎没有选择对象") 
            return {'FINISHED'}
        # 创建一个字典来存储顶点组的信息
        vertex_group_info = {}
        for group in SourceMesh.vertex_groups:
            vertex_group_info[group.name] = []

        # 遍历每个顶点
        for vertex in SourceMesh.data.vertices:
            for group in vertex.groups: #遍历单个顶点的顶点组
                group_index = group.group
                group_name = SourceMesh.vertex_groups[group_index].name
                weight = group.weight

                # 将顶点和权重信息添加到字典中
                vertex_group_info[group_name].append((vertex.index, weight))

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = SourceArmature
        bpy.ops.object.mode_set(mode='EDIT')
        selected_count = 0
        for bone in SourceArmature.data.edit_bones:
            bone.select = False
            if bone.name in vertex_group_info and vertex_group_info[bone.name]:
                bone.select = True
                selected_count += 1
        bpy.ops.object.mode_set(mode='POSE')

        self.report({'INFO'}, f"已选择 {selected_count} 个有权重骨骼")
        return {'FINISHED'}
    
class O_SelectUnweightedBones(bpy.types.Operator):
    bl_idname = "xqfa.vertex_groups_remove_bone_number"
    bl_label = "选择无权重骨骼"
    bl_description = "选择绑定到当前网格物体且无权重的骨骼"
    
    def execute(self, context):
        try:
            SourceMesh = bpy.data.objects.get(context.scene.vg_source_mesh.name)
            SourceArmature = bpy.data.objects.get(context.scene.vg_source_armature.name)
        except:
            self.report({'ERROR'}, "似乎没有选择对象") 
            return {'FINISHED'}
        # 创建一个字典来存储顶点组的信息
        vertex_group_info = {}
        for group in SourceMesh.vertex_groups:
            vertex_group_info[group.name] = []

        # 遍历每个顶点
        for vertex in SourceMesh.data.vertices:
            for group in vertex.groups:
                group_index = group.group
                group_name = SourceMesh.vertex_groups[group_index].name
                weight = group.weight
                vertex_group_info[group_name].append((vertex.index, weight))

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = SourceArmature
        bpy.ops.object.mode_set(mode='EDIT')
        selected_count = 0
        for bone in SourceArmature.data.edit_bones:
            bone.select = False
            if bone.name not in vertex_group_info or not vertex_group_info[bone.name]:
                bone.select = True
                selected_count += 1
        bpy.ops.object.mode_set(mode='POSE')

        self.report({'INFO'}, f"已选择 {selected_count} 个无权重骨骼")
        return {'FINISHED'}

########################## Divider ##########################


def get_armature_objects(context, armature):
    """获取场景中绑定到特定骨架的物体"""
    armature_objs = []
    for obj in context.scene.objects:
        if obj.type == 'MESH':
            # 遍历物体的修改器，寻找指向当前骨架的 Armature 修改器
            for mod in obj.modifiers:
                if mod.type == 'ARMATURE' and mod.object == armature:
                    armature_objs.append(obj)
                    break # 找到一个匹配的修改器即可
    return armature_objs

def _vg_vert_indices(vg, mesh):
    """获取顶点组中的顶点索引列表，兼容 Blender 5.2+（VertexGroup.vertices 被移除）"""
    if hasattr(vg, 'vertices'):
        return list(vg.vertices)
    # 兼容 Blender 5.2+：手动构建
    idx = vg.index
    return [v.index for v in mesh.vertices for g in v.groups if g.group == idx]

def merge_vertex_groups(obj, source_bone, target_bone):
    """将源顶点组的权重合并到目标顶点组"""
    if source_bone not in obj.vertex_groups or target_bone not in obj.vertex_groups:
        return
    
    mesh = obj.data
    vg_source = obj.vertex_groups[source_bone]
    vg_target = obj.vertex_groups[target_bone]
    src_idx = vg_source.index
    tgt_idx = vg_target.index
    
    # 只遍历源顶点组中的顶点，而非全部顶点
    src_verts = _vg_vert_indices(vg_source, mesh)
    if not src_verts:
        return
    
    # 预构建目标顶点组的顶点集合，用于快速判断
    tgt_vert_set = set(_vg_vert_indices(vg_target, mesh))
    
    replace_list = []  # (顶点索引, 叠加后权重) — 已在target中
    new_list = []      # (顶点索引, 源权重) — 不在target中
    
    for vi in src_verts:
        v = mesh.vertices[vi]
        src_w = None
        tgt_w = None
        # 单次遍历同时查找源权重和目标权重
        for g in v.groups:
            if g.group == src_idx:
                src_w = g.weight
            elif g.group == tgt_idx:
                tgt_w = g.weight
            if src_w is not None and tgt_w is not None:
                break
        if src_w is None:
            continue
        
        if tgt_w is not None:
            replace_list.append((vi, src_w + tgt_w))
        else:
            new_list.append((vi, src_w))
    
    # 批量更新已有顶点的权重
    for vi, w in replace_list:
        vg_target.add([vi], w, 'REPLACE')
    
    # 批量添加新顶点
    for vi, w in new_list:
        vg_target.add([vi], w, 'REPLACE')

class BONE_OT_merge_to_parent(bpy.types.Operator):
    """将选择的骨骼合并到它们的父级骨骼，影响顶点组"""
    bl_idname = "xqfa.merge_to_parent"
    bl_label = "将选择骨骼合并到父级"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and 
                context.active_object and 
                context.active_object.type == 'ARMATURE' and 
                context.selected_pose_bones)

    def execute(self, context):
        armature = context.active_object
        selected_bones = context.selected_pose_bones
        armature_objs = get_armature_objects(context, armature)
        
        # 按层级从高到低排序选择的骨骼，收集合并对
        sorted_bones = sorted(selected_bones, key=lambda b: len(b.parent_recursive), reverse=True)
        merge_pairs = []  # (bone_name, parent_name)
        for bone in sorted_bones:
            if bone.parent:
                merge_pairs.append((bone.name, bone.parent.name))
            else:
                self.report({'WARNING'}, f"骨骼 {bone.name} 没有父级，跳过")
        
        if not merge_pairs:
            return {'CANCELLED'}
        
        # 一次性切到 EDIT 模式处理所有骨骼关系
        bpy.ops.object.mode_set(mode='EDIT')
        bones_to_remove = []
        
        for bone_name, parent_name in merge_pairs:
            edit_bone = armature.data.edit_bones.get(bone_name)
            if not edit_bone:
                continue
            
            # 将所有子骨骼的父级设置为当前骨骼的父级
            parent_eb = armature.data.edit_bones.get(parent_name)
            if parent_eb:
                for child in edit_bone.children:
                    child.parent = parent_eb
            
            # 处理顶点组
            for obj in armature_objs:
                if bone_name not in obj.vertex_groups:
                    obj.vertex_groups.new(name=bone_name)
                if parent_name not in obj.vertex_groups:
                    obj.vertex_groups.new(name=parent_name)
                merge_vertex_groups(obj, bone_name, parent_name)
                if bone_name in obj.vertex_groups:
                    obj.vertex_groups.remove(obj.vertex_groups[bone_name])
            
            bones_to_remove.append(edit_bone)
        
        # 批量删除骨骼
        for eb in bones_to_remove:
            armature.data.edit_bones.remove(eb)
        
        bpy.ops.object.mode_set(mode='POSE')
        return {'FINISHED'}

class BONE_OT_merge_to_active(bpy.types.Operator):
    """将选择的骨骼合并到活动骨骼，影响顶点组"""
    bl_idname = "xqfa.merge_to_active"
    bl_label = "将选择骨骼合并到活动骨骼"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and 
                context.active_object and 
                context.active_object.type == 'ARMATURE' and 
                context.selected_pose_bones and 
                context.active_pose_bone and 
                len(context.selected_pose_bones) > 1)

    def execute(self, context):
        armature = context.active_object
        selected_bones = context.selected_pose_bones
        active_bone = context.active_pose_bone
        armature_objs = get_armature_objects(context, armature)
        
        # 确保活动骨骼在选中的骨骼中
        if active_bone not in selected_bones:
            self.report({'ERROR'}, "活动骨骼必须在选择的骨骼中")
            return {'CANCELLED'}
            
        # 从选中的骨骼中移除活动骨骼，收集合并对
        active_bone_name = active_bone.name
        bones_to_merge = [b for b in selected_bones if b != active_bone]
        sorted_bones = sorted(bones_to_merge, key=lambda b: len(b.parent_recursive), reverse=True)
        
        if not sorted_bones:
            return {'CANCELLED'}
        
        # 一次性切到 EDIT 模式处理所有骨骼关系
        bpy.ops.object.mode_set(mode='EDIT')
        bones_to_remove = []
        
        for bone in sorted_bones:
            bone_name = bone.name
            edit_bone = armature.data.edit_bones.get(bone_name)
            if not edit_bone:
                continue
            
            # 将所有子骨骼的父级设置为活动骨骼
            active_eb = armature.data.edit_bones.get(active_bone_name)
            if active_eb:
                for child in edit_bone.children:
                    child.parent = active_eb
            
            # 处理顶点组
            for obj in armature_objs:
                if bone_name not in obj.vertex_groups:
                    obj.vertex_groups.new(name=bone_name)
                if active_bone_name not in obj.vertex_groups:
                    obj.vertex_groups.new(name=active_bone_name)
                merge_vertex_groups(obj, bone_name, active_bone_name)
                if bone_name in obj.vertex_groups:
                    obj.vertex_groups.remove(obj.vertex_groups[bone_name])
            
            bones_to_remove.append(edit_bone)
        
        # 批量删除骨骼
        for eb in bones_to_remove:
            armature.data.edit_bones.remove(eb)
        
        bpy.ops.object.mode_set(mode='POSE')
        return {'FINISHED'}


########################## Divider ##########################

class VG_OT_merge_to_parent(bpy.types.Operator):
    """将选中骨骼对应的顶点组合并到其父级骨骼的顶点组（不删除骨骼）"""
    bl_idname = "xqfa.vg_merge_to_parent"
    bl_label = "顶点组合并到父级"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and
                context.active_object and
                context.active_object.type == 'ARMATURE' and
                context.selected_pose_bones)

    def execute(self, context):
        try:
            source_mesh = bpy.data.objects.get(context.scene.vg_source_mesh.name)
        except:
            self.report({'ERROR'}, "请先选择网格对象")
            return {'CANCELLED'}

        if not source_mesh:
            self.report({'ERROR'}, "请先选择网格对象")
            return {'CANCELLED'}

        selected_bones = context.selected_pose_bones
        sorted_bones = sorted(selected_bones, key=lambda b: len(b.parent_recursive), reverse=True)

        merged_count = 0
        for bone in sorted_bones:
            bone_name = bone.name
            parent_bone = bone.parent

            if not parent_bone:
                self.report({'WARNING'}, f"骨骼 {bone_name} 没有父级，跳过")
                continue

            parent_name = parent_bone.name

            if bone_name not in source_mesh.vertex_groups:
                source_mesh.vertex_groups.new(name=bone_name)
            if parent_name not in source_mesh.vertex_groups:
                source_mesh.vertex_groups.new(name=parent_name)

            merge_vertex_groups(source_mesh, bone_name, parent_name)

            if bone_name in source_mesh.vertex_groups:
                source_mesh.vertex_groups.remove(source_mesh.vertex_groups[bone_name])

            merged_count += 1

        self.report({'INFO'}, f"已合并 {merged_count} 个顶点组到父级")
        return {'FINISHED'}


class VG_OT_merge_to_active(bpy.types.Operator):
    """将选中骨骼对应的顶点组合并到活动骨骼的顶点组（不删除骨骼）"""
    bl_idname = "xqfa.vg_merge_to_active"
    bl_label = "顶点组合并到活动"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and
                context.active_object and
                context.active_object.type == 'ARMATURE' and
                context.selected_pose_bones and
                context.active_pose_bone and
                len(context.selected_pose_bones) > 1)

    def execute(self, context):
        try:
            source_mesh = bpy.data.objects.get(context.scene.vg_source_mesh.name)
        except:
            self.report({'ERROR'}, "请先选择网格对象")
            return {'CANCELLED'}

        if not source_mesh:
            self.report({'ERROR'}, "请先选择网格对象")
            return {'CANCELLED'}

        selected_bones = context.selected_pose_bones
        active_bone = context.active_pose_bone

        if active_bone not in selected_bones:
            self.report({'ERROR'}, "活动骨骼必须在选择的骨骼中")
            return {'CANCELLED'}

        bones_to_merge = [b for b in selected_bones if b != active_bone]
        active_bone_name = active_bone.name
        sorted_bones = sorted(bones_to_merge, key=lambda b: len(b.parent_recursive), reverse=True)

        merged_count = 0
        for bone in sorted_bones:
            bone_name = bone.name

            if bone_name not in source_mesh.vertex_groups:
                source_mesh.vertex_groups.new(name=bone_name)
            if active_bone_name not in source_mesh.vertex_groups:
                source_mesh.vertex_groups.new(name=active_bone_name)

            merge_vertex_groups(source_mesh, bone_name, active_bone_name)

            if bone_name in source_mesh.vertex_groups:
                source_mesh.vertex_groups.remove(source_mesh.vertex_groups[bone_name])

            merged_count += 1

        self.report({'INFO'}, f"已合并 {merged_count} 个顶点组到活动骨骼")
        return {'FINISHED'}


class VG_OT_delete_corresponding(bpy.types.Operator):
    """删除选中骨骼对应的顶点组（不删除骨骼）"""
    bl_idname = "xqfa.vg_delete_corresponding"
    bl_label = "删除对应顶点组"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'POSE' and
                context.active_object and
                context.active_object.type == 'ARMATURE' and
                context.selected_pose_bones)

    def execute(self, context):
        try:
            source_mesh = bpy.data.objects.get(context.scene.vg_source_mesh.name)
        except:
            self.report({'ERROR'}, "请先选择网格对象")
            return {'CANCELLED'}

        if not source_mesh:
            self.report({'ERROR'}, "请先选择网格对象")
            return {'CANCELLED'}

        deleted_count = 0
        for bone in context.selected_pose_bones:
            if bone.name in source_mesh.vertex_groups:
                source_mesh.vertex_groups.remove(source_mesh.vertex_groups[bone.name])
                deleted_count += 1

        self.report({'INFO'}, f"已删除 {deleted_count} 个对应顶点组")
        return {'FINISHED'}


########################## Divider ##########################

def _read_csv_file(filepath):
    """读取CSV文件，返回 (csv_data, error_message)"""
    if not filepath or not os.path.exists(filepath):
        return None, "请选择有效的CSV文件"

    encodings = ['utf-8', 'gbk', 'utf-16']
    for encoding in encodings:
        try:
            with open(filepath, 'r', newline='', encoding=encoding) as file:
                reader = csv.reader(file)
                csv_data = list(reader)
            return csv_data, None
        except UnicodeDecodeError:
            continue
        except Exception as e:
            return None, f"导入CSV文件时出现错误: {e}"

    return None, "无法解码CSV文件，请尝试转换为UTF-8编码"


class O_BoneSimpleMapping(bpy.types.Operator, ImportHelper):
    bl_idname = "xqfa.simple_mapping"
    bl_label = "简化骨骼"
    bl_description = "根据CSV映射表保留主骨骼、处理合并逻辑并清理多余骨骼"
    filename_ext = ".csv"
    filter_glob: bpy.props.StringProperty(
        default="*.csv",
        options={'HIDDEN'},
    )

    def execute(self, context):
        scene = context.scene
        target_obj = context.active_object
        if not target_obj or target_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请先选中一个骨架对象")
            return {'CANCELLED'}

        csv_data, err = _read_csv_file(self.filepath)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}

        # 2. 提取配置
        cols = {
            'main': scene.simple_main_column,
            'save': scene.simple_save_column,
            'active': scene.simple_active_column,
            'to_active': scene.simple_toactive_column
        }
        
        bone_main = set()
        bone_save = set()
        bone_mapping = {}

        # 3. 单次遍历解析 CSV 数据
        for row in csv_data[1:]:
            row_len = len(row)
            
            for key, attr in [('main', bone_main), ('save', bone_save)]:
                idx = cols[key]
                if row_len > idx:
                    val = str(row[idx]).strip()
                    if val and val != "None":
                        attr.add(val)

            m_idx, t_idx = cols['active'], cols['to_active']
            if row_len > max(m_idx, t_idx):
                key_bone, val_bone = str(row[t_idx]).strip(), str(row[m_idx]).strip()
                if all([key_bone, val_bone, key_bone != "None", val_bone != "None"]):
                    bone_mapping[key_bone] = val_bone

        # 4. 分配集合与颜色（预过滤不存在的骨骼名）
        pose_bone_names = set(target_obj.pose.bones.keys())
        valid_main = bone_main & pose_bone_names
        valid_save = bone_save & pose_bone_names
        
        def assign_bones_to_collection(armature, bone_names, coll_name, palette):
            if not bone_names: return
            coll = armature.data.collections.get(coll_name) or armature.data.collections.new(coll_name)
            for name in bone_names:
                p_bone = armature.pose.bones.get(name)
                if p_bone:
                    coll.assign(p_bone.bone)
                    p_bone.bone.color.palette = palette

        # 进入姿态模式
        bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.objects.active = target_obj
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.reveal()

        # 5. 分配集合与颜色
        assign_bones_to_collection(target_obj, valid_main, "主骨骼", 'THEME02')
        assign_bones_to_collection(target_obj, valid_save, "保留骨骼", 'THEME09')

        # 6+7+8. 一次性切到 EDIT 模式，批量处理所有合并与删除
        armature_objs = get_armature_objects(context, target_obj)
        
        # 收集步骤6的合并对（特定合并），过滤不存在的骨骼
        mapping_pairs = [(src, tgt) for src, tgt in bone_mapping.items()
                         if src in pose_bone_names and tgt in pose_bone_names]
        
        # 收集步骤7的合并对（剩余骨骼合并至父级）
        keep_bones = bone_main.union(bone_save)
        bones_to_parent_names = pose_bone_names - keep_bones
        
        # 按层级从高到低排序，避免先删父级再处理子级的问题
        parent_pairs = []
        for b_name in bones_to_parent_names:
            pb = target_obj.pose.bones.get(b_name)
            if pb and pb.parent:
                parent_pairs.append((b_name, pb.parent.name))
        parent_pairs.sort(key=lambda p: len(target_obj.pose.bones[p[0]].parent_recursive), reverse=True)
        
        # 合并两组操作
        all_merge_pairs = mapping_pairs + parent_pairs
        bones_to_delete = set(b_name for b_name, _ in parent_pairs)
        
        if all_merge_pairs:
            bpy.ops.object.mode_set(mode='EDIT')
            edit_bones = target_obj.data.edit_bones
            
            for bone_name, target_name in all_merge_pairs:
                edit_bone = edit_bones.get(bone_name)
                if not edit_bone:
                    continue
                
                # 将子骨骼的父级重指向目标骨骼
                target_eb = edit_bones.get(target_name)
                if target_eb:
                    for child in list(edit_bone.children):
                        child.parent = target_eb
                
                # 处理顶点组
                for obj in armature_objs:
                    if bone_name not in obj.vertex_groups:
                        obj.vertex_groups.new(name=bone_name)
                    if target_name not in obj.vertex_groups:
                        obj.vertex_groups.new(name=target_name)
                    merge_vertex_groups(obj, bone_name, target_name)
                    if bone_name in obj.vertex_groups:
                        obj.vertex_groups.remove(obj.vertex_groups[bone_name])
                
                bones_to_delete.add(bone_name)
            
            # 批量删除骨骼
            for b_name in bones_to_delete:
                eb = edit_bones.get(b_name)
                if eb:
                    edit_bones.remove(eb)
            
            bpy.ops.object.mode_set(mode='POSE')

        # 9. 清理工作
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.pose.constraints_clear()
        
        self.report({'INFO'}, "简化骨骼操作完成")
        return {'FINISHED'}


class O_BoneRenameMapping(bpy.types.Operator, ImportHelper):
    bl_idname = "xqfa.bone_rename_mapping"
    bl_label = "重命名"
    bl_description = "将源骨架骨骼按csv对应, 重命名"
    filename_ext = ".csv"
    filter_glob: bpy.props.StringProperty(
        default="*.csv",
        options={'HIDDEN'},
    )

    def execute(self, context):
        TargetArmature = context.active_object
        if not TargetArmature or TargetArmature.type != 'ARMATURE':
            self.report({'ERROR'}, "请先选中一个骨架对象")
            return {'CANCELLED'}

        csv_data, err = _read_csv_file(self.filepath)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
        current_skel_column = context.scene.current_skel_column
        change_skel_column = context.scene.change_skel_column
        bone_mapping = {}
        for row in csv_data[1:]:
            if len(row) <= max(current_skel_column, change_skel_column):
                continue
            key = str(row[current_skel_column]).strip()
            value = str(row[change_skel_column]).strip()
            if not key or not value or key == "None" or value == "None":
                continue
            bone_mapping[key] = value

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = TargetArmature
        bpy.ops.object.mode_set(mode='POSE')
        rename_count = 0
        for current_bone_name, change_bone_name in bone_mapping.items():
            try:
                TargetArmature.data.bones[current_bone_name].name = change_bone_name
                rename_count += 1
            except:
                print(f"{current_bone_name}不存在")

        scene = context.scene
        if hasattr(scene, 'xqfa_vertex_group_mappings'):
            mappings = scene.xqfa_vertex_group_mappings
            item = mappings.add()
            item.label = f"重命名映射 {len(mappings)}"
            item.expanded = False
            for current_bone_name, change_bone_name in bone_mapping.items():
                p = item.pairs.add()
                p.left_name = current_bone_name
                p.right_name = change_bone_name
                p.similarity = ""

        self.report({'INFO'}, f"已重命名 {rename_count} 个骨骼")
        return {'FINISHED'}


class O_BoneCSVSelect(bpy.types.Operator, ImportHelper):
    bl_idname = "xqfa.csv_bone_sel"
    bl_label = "选择骨骼"
    bl_description = "导入CSV并按指定列选择骨骼"
    filename_ext = ".csv"
    filter_glob: bpy.props.StringProperty(
        default="*.csv",
        options={'HIDDEN'},
    )

    def execute(self, context):
        scene = context.scene
        target_obj = context.active_object
        if not target_obj or target_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "请先选中一个骨架对象")
            return {'CANCELLED'}
        if target_obj.mode != 'POSE':
            self.report({'ERROR'}, "请切换到姿态模式")
            return {'CANCELLED'}

        csv_data, err = _read_csv_file(self.filepath)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}

        bone_sel_col = scene.bone_sel_col
        bone_sel = []

        for row in csv_data[1:]:
            if len(row) <= bone_sel_col:
                continue
            value = str(row[bone_sel_col]).strip()
            if not value or value == "None":
                continue
            bone_sel.append(value)

        # 选择骨骼
        bpy.ops.pose.select_all(action='DESELECT')
        selected_count = 0
        for bone_name in bone_sel:
            if bone_name in target_obj.pose.bones:
                _select_pose_bone(target_obj.pose.bones[bone_name])
                selected_count += 1

        self.report({'INFO'}, f"已选择 {selected_count}/{len(bone_sel)} 个骨骼")
        return {'FINISHED'}


class O_BonePosePrint(bpy.types.Operator):
    bl_idname = "xqfa.pose_print"
    bl_label = "复制选中骨骼名称"
    bl_description = "打印并复制选择的骨骼名称到剪贴板"

    @classmethod
    def poll(cls, context):
        """检查是否满足操作条件"""
        # 必须有一个选中的物体，且是骨架类型，并且当前处于姿态模式
        return (context.object and
                context.object.type == 'ARMATURE' and
                context.object.mode == 'POSE' and
                context.selected_pose_bones)

    def execute(self, context):
        selected_bones = context.selected_pose_bones
        if not selected_bones:
            self.report({'WARNING'}, "没有选择任何骨骼")
            return {"CANCELLED"}

        # 收集所有骨骼名称
        bone_names = [bone.name for bone in selected_bones]
        output_text = "\n".join(bone_names)

        # 打印到控制台
        print("选择的骨骼名称:")
        print(output_text)

        # 复制到Blender剪贴板
        try:
            context.window_manager.clipboard = output_text
            self.report({'INFO'}, f"已复制 {len(bone_names)} 个骨骼名称到剪贴板")
        except Exception as e:
            self.report({'ERROR'}, f"复制到剪贴板失败: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}


########################## Divider ##########################

def auto_set_vg_armature_handler(scene, depsgraph):
    """进入姿态模式时自动设置 vg_source_armature 为活动骨架"""
    if scene.vg_source_armature is None:
        for obj in scene.objects:
            if obj.type == 'ARMATURE' and obj.mode == 'POSE':
                scene.vg_source_armature = obj
                break


class P_VertexGroups(bpy.types.Panel):
    bl_idname = "X_PT_VertexGroups"
    bl_label = "骨骼与顶点组"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XQFA'

    @classmethod
    def poll(cls, context):
        # 只有当主面板激活了此子面板时才显示
        return getattr(context.scene, 'active_xbone_subpanel', '') == 'BoneTools'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator(BONE_OT_merge_to_parent.bl_idname, text="合并到父级", icon="BONE_DATA")
        row.operator(BONE_OT_merge_to_active.bl_idname, text="合并到活动", icon="BONE_DATA")

        box = layout.box()

        col = box.column(align=True)
        col.prop(context.scene, "vg_source_armature", text="", icon="ARMATURE_DATA")
        col.prop(context.scene, "vg_source_mesh", text="", icon="MESH_DATA")
        row = col.row(align=True)
        row.operator(VG_OT_merge_to_parent.bl_idname, text=VG_OT_merge_to_parent.bl_label, icon="GROUP_VERTEX")
        row.operator(VG_OT_merge_to_active.bl_idname, text=VG_OT_merge_to_active.bl_label, icon="GROUP_VERTEX")
        col.operator(VG_OT_delete_corresponding.bl_idname, text=VG_OT_delete_corresponding.bl_label, icon="TRASH")
        row = col.row(align=True)
        row.operator(O_NoVgDelBone.bl_idname, text=O_NoVgDelBone.bl_label, icon="BONE_DATA")
        row.operator(O_NoBoneDelVg.bl_idname, text=O_NoBoneDelVg.bl_label, icon="GROUP_VERTEX")
        row = col.row(align=True)
        row.operator(O_SelectWeightedBones.bl_idname, text=O_SelectWeightedBones.bl_label, icon="LINENUMBERS_ON")
        row.operator(O_SelectUnweightedBones.bl_idname, text=O_SelectUnweightedBones.bl_label, icon="LINENUMBERS_ON")


        box = layout.box()
        
        box.operator(O_BonePosePrint.bl_idname, text=O_BonePosePrint.bl_label, icon='COPYDOWN')

        row = box.row(align=True)
        row.prop(context.scene, "bone_sel_col")
        row.operator(O_BoneCSVSelect.bl_idname, text=O_BoneCSVSelect.bl_label, icon="PLAY")
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(context.scene, "simple_main_column")
        row.prop(context.scene, "simple_save_column")
        row = col.row(align=True)
        row.prop(context.scene, "simple_active_column")
        row.prop(context.scene, "simple_toactive_column")
        col.operator(O_BoneSimpleMapping.bl_idname, icon="PLAY")

        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(context.scene, "current_skel_column")
        row.prop(context.scene, "change_skel_column")
        col.operator(O_BoneRenameMapping.bl_idname, icon="PLAY")



########################## Divider ##########################

def register():
    bpy.utils.register_class(O_NoVgDelBone)
    bpy.utils.register_class(O_NoBoneDelVg)
    bpy.utils.register_class(O_SelectWeightedBones)
    bpy.utils.register_class(O_SelectUnweightedBones)
    bpy.utils.register_class(BONE_OT_merge_to_parent)
    bpy.utils.register_class(BONE_OT_merge_to_active)
    bpy.utils.register_class(VG_OT_merge_to_parent)
    bpy.utils.register_class(VG_OT_merge_to_active)
    bpy.utils.register_class(VG_OT_delete_corresponding)
    bpy.utils.register_class(O_BoneSimpleMapping)
    bpy.utils.register_class(O_BoneRenameMapping)
    bpy.utils.register_class(O_BoneCSVSelect)
    bpy.utils.register_class(O_BonePosePrint)
    bpy.utils.register_class(P_VertexGroups)

    bpy.types.Scene.vg_source_mesh = bpy.props.PointerProperty(type=bpy.types.Object, poll=ObjType.is_mesh)
    bpy.types.Scene.vg_source_armature = bpy.props.PointerProperty(type=bpy.types.Object, poll=ObjType.is_armature)

    bpy.types.Scene.simple_main_column = bpy.props.IntProperty(
        name="主骨骼",
        description="主要骨骼的列索引",
        default=1,
        min=0,
    )
    bpy.types.Scene.simple_save_column = bpy.props.IntProperty(
        name="保留骨",
        description="可以后续调整物理的骨骼列索引",
        default=2,
        min=0,
    )
    bpy.types.Scene.simple_active_column = bpy.props.IntProperty(
        name="指定骨",
        description="",
        default=3,
        min=0,
    )
    bpy.types.Scene.simple_toactive_column = bpy.props.IntProperty(
        name="合并到指定",
        description="会被合并至指定的骨骼",
        default=4,
        min=0,
    )
    bpy.types.Scene.current_skel_column = bpy.props.IntProperty(
        name="源名称",
        description="源名称改为目标名称\n0是第1列",
        default=1,
        min=0,
    )
    bpy.types.Scene.change_skel_column = bpy.props.IntProperty(
        name="目标名称",
        description="源名称改为目标名称\n0是第1列",
        default=0,
        min=0,
    )
    bpy.types.Scene.bone_sel_col = bpy.props.IntProperty(
        name="索引",
        default=0,
        min=0,
    )

    bpy.app.handlers.depsgraph_update_post.append(auto_set_vg_armature_handler)

def unregister():
    bpy.utils.unregister_class(O_NoVgDelBone)
    bpy.utils.unregister_class(O_NoBoneDelVg)
    bpy.utils.unregister_class(O_SelectWeightedBones)
    bpy.utils.unregister_class(O_SelectUnweightedBones)
    bpy.utils.unregister_class(BONE_OT_merge_to_parent)
    bpy.utils.unregister_class(BONE_OT_merge_to_active)
    bpy.utils.unregister_class(VG_OT_merge_to_parent)
    bpy.utils.unregister_class(VG_OT_merge_to_active)
    bpy.utils.unregister_class(VG_OT_delete_corresponding)
    bpy.utils.unregister_class(O_BoneSimpleMapping)
    bpy.utils.unregister_class(O_BoneRenameMapping)
    bpy.utils.unregister_class(O_BoneCSVSelect)
    bpy.utils.unregister_class(O_BonePosePrint)
    bpy.utils.unregister_class(P_VertexGroups)

    if auto_set_vg_armature_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(auto_set_vg_armature_handler)

    del bpy.types.Scene.vg_source_mesh
    del bpy.types.Scene.vg_source_armature

    del bpy.types.Scene.simple_main_column
    del bpy.types.Scene.simple_save_column
    del bpy.types.Scene.simple_toactive_column
    del bpy.types.Scene.simple_active_column
    del bpy.types.Scene.current_skel_column
    del bpy.types.Scene.change_skel_column
    del bpy.types.Scene.bone_sel_col