# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import math
import re
import traceback

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, FloatProperty

from .spine_import import import_jsonfile

bl_info = {
    "name": "spine_blender",
    "author": "reclizer",
    "description": "导入 Spine2D 骨骼动画 (json + atlas) 到 Blender",
    "blender": (2, 83, 0),
    "version": (0, 0, 2),
    "location": "3D视图 > 侧边栏 > SToB",
    "warning": "",
    "category": "Import-Export",
}


class SpineJsonImportMixin(ImportHelper):
    """三个 json 导入操作共用的文件选择和错误处理逻辑"""
    filename_ext = ".json"
    filter_glob: StringProperty(  # type: ignore
        default="*.json",
        options={"HIDDEN"},
        maxlen=255,
    )

    # 子类用这两个开关控制 import_jsonfile 的行为
    add_mode = False
    reload_mode = False

    def draw(self, context):
        box = self.layout.box()
        box.label(text="Settings:", icon="IMPORT")

    def execute(self, context):
        try:
            import_jsonfile(self.filepath, self.add_mode, self.reload_mode)
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, f"导入失败: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


class ImportJsonOperator(bpy.types.Operator, SpineJsonImportMixin):
    bl_idname = "spine.import_json"
    bl_label = "Import JSON File"
    bl_description = "导入 Spine 的 json/atlas, 生成骨骼、网格和动画"
    bl_options = {'REGISTER', 'UNDO'}


class AddJsonOperator(bpy.types.Operator, SpineJsonImportMixin):
    bl_idname = "spine.add_json"
    bl_label = "Add JSON File"
    bl_description = "追加导入一个 Spine 文件, 并把新旧贴图合并成一张"
    bl_options = {'REGISTER', 'UNDO'}

    add_mode = True


class ReloadJsonOperator(bpy.types.Operator, SpineJsonImportMixin):
    bl_idname = "spine.reload_json"
    bl_label = "reload atlas File"
    bl_description = "按图集重建已有网格的 UV 并刷新贴图路径"
    bl_options = {'REGISTER', 'UNDO'}

    reload_mode = True


class ClearVertexGroup(bpy.types.Operator):
    bl_idname = "spine.clear_vertex_group"
    bl_label = "Clear Vertex Group"
    bl_description = "删除所选网格上没有对应骨骼的顶点组(需同时选中骨架)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bone_names = set()
        for obj in context.selected_objects:
            if obj.type == 'ARMATURE':
                for bone in obj.data.bones:
                    bone_names.add(bone.name.strip())

        if not bone_names:
            # 没选骨架时骨骼名单为空, 会把顶点组全删光, 直接拦下
            self.report({'WARNING'}, "请同时选中骨架和网格物体")
            return {'CANCELLED'}

        removed = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            # 先复制列表再删, 避免边遍历边删除时跳项
            for group in list(obj.vertex_groups):
                if group.name.strip() not in bone_names:
                    obj.vertex_groups.remove(group)
                    removed += 1

        self.report({'INFO'}, f"删除了 {removed} 个无效顶点组")
        return {'FINISHED'}


class FixVertexGroup(bpy.types.Operator):
    bl_idname = "spine.fix_vertex_group"
    bl_label = "Fix Vertex Group"
    bl_description = "把没有任何权重的顶点绑到 root 顶点组"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        group_new = 0
        vert_fixed = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue

            if not obj.vertex_groups:
                root_group = obj.vertex_groups.new(name="root")
                root_group.add([v.index for v in obj.data.vertices], 1.0, 'REPLACE')
                group_new += 1
                continue

            # v.groups 直接给出顶点所属的顶点组, 不需要逐组试探权重
            empty_verts = [v.index for v in obj.data.vertices
                           if not any(g.weight > 0 for g in v.groups)]
            if empty_verts:
                root_group = (obj.vertex_groups.get("root")
                              or obj.vertex_groups.new(name="root"))
                root_group.add(empty_verts, 1.0, 'REPLACE')
                vert_fixed += len(empty_verts)

        self.report({'INFO'}, f"补权重顶点 {vert_fixed} 个, 新建 root 组 {group_new} 个")
        return {'FINISHED'}


class FixWeight(bpy.types.Operator):
    bl_idname = "spine.fix_weight"
    bl_label = "Fix Weight"
    bl_description = "把所选网格每个顶点的权重归一化"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        choose_num = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            choose_num += 1
            for v in obj.data.vertices:
                total_weight = sum(g.weight for g in v.groups)
                if total_weight > 0:
                    for g in v.groups:
                        g.weight /= total_weight

        self.report({'INFO'}, f"修改了 {choose_num} 个物体")
        return {'FINISHED'}


class ChooseVertexGroup(bpy.types.Operator):
    bl_idname = "spine.choose_vertex_group"
    bl_label = "Choose Vertex Group"
    bl_description = "选中场景里所有包含 root 顶点组的网格"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.object.select_all(action='DESELECT')
        choose_num = 0
        for obj in context.scene.objects:
            if obj.type == 'MESH' and "root" in obj.vertex_groups:
                obj.select_set(True)
                choose_num += 1

        if context.selected_objects:
            context.view_layer.objects.active = context.selected_objects[-1]
        self.report({'INFO'}, f"选中了 {choose_num} 个物体")
        return {'FINISHED'}


class ApplyAnmiScale(bpy.types.Operator):
    bl_idname = "spine.apply_anmi_scale"
    bl_label = "Apply Anmi Scale"
    bl_description = "把骨架物体的缩放应用到动画的位移关键帧上"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        armature_obj = context.active_object
        if not armature_obj or armature_obj.type != 'ARMATURE':
            self.report({'WARNING'}, "请先激活一个骨架物体")
            return {'CANCELLED'}

        anim_data = armature_obj.animation_data
        if not anim_data or not anim_data.action:
            self.report({'WARNING'}, f"{armature_obj.name} 没有动画数据")
            return {'CANCELLED'}

        scale_factor = armature_obj.scale.x
        for fcurve in anim_data.action.fcurves:
            # 只缩放位移曲线, 旋转不受物体缩放影响
            if fcurve.data_path.endswith("location"):
                for keyframe in fcurve.keyframe_points:
                    keyframe.co.y *= scale_factor
                    keyframe.handle_left.y *= scale_factor
                    keyframe.handle_right.y *= scale_factor

        self.report({'INFO'}, f"应用了 {scale_factor} 倍缩放")
        return {'FINISHED'}


class SelectWeakAnimBones(bpy.types.Operator):
    bl_idname = "spine.select_weak_anim_bones"
    bl_label = "Select Weak Anim Bones"
    bl_description = "选中没有动画帧的骨骼, 以及所有旋转关键帧角度都小于阈值的骨骼"
    bl_options = {'REGISTER', 'UNDO'}

    angle_threshold: FloatProperty(  # type: ignore
        name="旋转角度阈值(度)",
        description="骨骼所有旋转关键帧的角度绝对值都小于该值时视为弱动画",
        default=1.0,
        min=0.0,
        max=180.0,
    )

    def execute(self, context):
        armature_obj = context.active_object
        if not armature_obj or armature_obj.type != 'ARMATURE':
            self.report({'WARNING'}, "请先激活一个骨架物体")
            return {'CANCELLED'}

        if context.mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')

        # 从当前动作统计每根骨骼的关键帧: 骨骼名 -> 旋转角绝对值的最大值(弧度)
        bone_keys = {}
        anim_data = armature_obj.animation_data
        action = anim_data.action if anim_data else None
        if action:
            path_re = re.compile(r'pose\.bones\["(.+?)"\]\.(\w+)')
            for fcurve in action.fcurves:
                match = path_re.match(fcurve.data_path)
                if not match or len(fcurve.keyframe_points) == 0:
                    continue
                bone_name, prop = match.groups()
                max_rot = bone_keys.setdefault(bone_name, 0.0)
                if prop == "rotation_euler":
                    peak = max(abs(kp.co.y) for kp in fcurve.keyframe_points)
                    bone_keys[bone_name] = max(max_rot, peak)

        threshold = math.radians(self.angle_threshold)
        no_anim = 0
        weak_rot = 0
        for pbone in armature_obj.pose.bones:
            max_rot = bone_keys.get(pbone.name)
            if max_rot is None:
                # 动作里没有这根骨骼的任何关键帧
                pbone.bone.select = True
                no_anim += 1
            elif max_rot < threshold:
                pbone.bone.select = True
                weak_rot += 1
            else:
                pbone.bone.select = False

        self.report({'INFO'}, f"选中 {no_anim} 根无动画骨骼, {weak_rot} 根弱旋转骨骼")
        return {'FINISHED'}


class SpineUIPanel(bpy.types.Panel):
    bl_label = "File"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SToB'

    def draw(self, context):
        layout = self.layout

        layout.label(text="Import:", icon="IMPORT")
        col = layout.column(align=True)
        col.operator("spine.import_json", icon="MESH_CUBE", text="加载JSON ...")
        col.operator("spine.add_json", icon="MESH_CUBE", text="追加JSON ...")
        col.operator("spine.reload_json", icon="MESH_CUBE", text="重载材质 ...")

        layout.label(text="Tools:", icon="TOOL_SETTINGS")
        col = layout.column(align=True)
        col.operator("spine.clear_vertex_group", icon="X", text="删除无效顶点组")
        col.operator("spine.fix_vertex_group", icon="GROUP_VERTEX", text="补全空顶点组")
        col.operator("spine.choose_vertex_group", icon="RESTRICT_SELECT_OFF", text="选择包含root组的物体")
        col.operator("spine.select_weak_anim_bones", icon="BONE_DATA", text="选择弱动画骨骼")
        col.operator("spine.fix_weight", icon="MOD_VERTEX_WEIGHT", text="权重归一")
        col.operator("spine.apply_anmi_scale", icon="CON_SIZELIKE", text="应用骨骼动画缩放")


classes = (
    ImportJsonOperator,
    AddJsonOperator,
    ReloadJsonOperator,
    ClearVertexGroup,
    FixVertexGroup,
    FixWeight,
    ChooseVertexGroup,
    ApplyAnmiScale,
    SelectWeakAnimBones,
    SpineUIPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
