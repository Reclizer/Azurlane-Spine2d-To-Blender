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

import bpy

from .spine_import import import_jsonfile
import os.path as path
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty
import json

bl_info = {
    "name" : "spine_blender",
    "author" : "reclizer",
    "description" : "",
    "blender" : (2, 80, 0),
    "version" : (0, 0, 1),
    "location" : "",
    "warning" : "",
    "category" : "Generic"
}

class ImportJsonOperator(bpy.types.Operator, ImportHelper):
    bl_idname = "spine.import_json"
    bl_label = "Import JSON File"

    filename_ext = ".json"
    filter_glob: StringProperty(# type: ignore
        default="*.json",
        options={"HIDDEN"},
        maxlen=255,
    )
    filepath: StringProperty( # type: ignore
        name="Import file Path",
        maxlen=1024,
    )
    
    def draw(self, context):
        box = self.layout.box()
        box.label(text="Settings:", icon="IMPORT")
    
    def execute(self, context):
        import_jsonfile(self.filepath)
        #self.report({'INFO'}, str(self.filepath))
        
        '''
        # 打开所选文件并加载 JSON 数据
        with open(self.filepath, 'r') as file:
            json_data = json.load(file)
            # 在这里处理加载的 JSON 数据，可以根据需要执行进一步的操作

        # 在控制台中打印加载的 JSON 数据（仅作为示例）
        print(json_data)
        '''
        # 返回操作完成标志
        return {'FINISHED'}

    def invoke(self, context, event):
        # 打开文件选择对话框
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class AddJsonOperator(bpy.types.Operator, ImportHelper):
    bl_idname = "spine.add_json"
    bl_label = "Add JSON File"

    filename_ext = ".json"
    filter_glob: StringProperty(# type: ignore
        default="*.json",
        options={"HIDDEN"},
        maxlen=255,
    )
    filepath: StringProperty( # type: ignore
        name="Import file Path",
        maxlen=1024,
    )
    
    def draw(self, context):
        box = self.layout.box()
        box.label(text="Settings:", icon="IMPORT")
    
    def execute(self, context):
        import_jsonfile(self.filepath,True)
        #self.report({'INFO'}, str(self.filepath))
        
        '''
        # 打开所选文件并加载 JSON 数据
        with open(self.filepath, 'r') as file:
            json_data = json.load(file)
            # 在这里处理加载的 JSON 数据，可以根据需要执行进一步的操作

        # 在控制台中打印加载的 JSON 数据（仅作为示例）
        print(json_data)
        '''
        # 返回操作完成标志
        return {'FINISHED'}

    def invoke(self, context, event):
        # 打开文件选择对话框
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class ReloadJsonOperator(bpy.types.Operator, ImportHelper):
    bl_idname = "spine.reload_json"
    bl_label = "reload atlas File"

    filename_ext = ".json"
    filter_glob: StringProperty(  # type: ignore
        default="*.json",
        options={"HIDDEN"},
        maxlen=255,
    )
    filepath: StringProperty(  # type: ignore
        name="Import file Path",
        maxlen=1024,
    )

    def draw(self, context):
        box = self.layout.box()
        box.label(text="Settings:", icon="IMPORT")

    def execute(self, context):
        import_jsonfile(self.filepath, False,True)

        # 返回操作完成标志
        return {'FINISHED'}

    def invoke(self, context, event):
        # 打开文件选择对话框
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class ClearVertexGroup(bpy.types.Operator):
    bl_idname = "spine.clear_vertex_group"
    bl_label = "Clear Vertex Group"
    bl_description = "Clear specified vertex group from selected mesh objects"

    #group_name: bpy.props.StringProperty(name="Group Name", default="Group_Name")

    def execute(self, context):
        selected_objects = context.selected_objects
        bone_list=[]
        group_num=0
        for obj in selected_objects:
            if obj.type == 'ARMATURE':  
                armature = obj.data
                for bone in armature.bones:
                    bone_list.append(str(bone.name.strip())) 

        for obj in selected_objects:
            if obj.type == 'MESH':  
                vertex_groups = obj.vertex_groups
                for group in vertex_groups:
                    group_name=str(group.name.strip())
                    #print(group_name)
                    if not group_name in bone_list:
                        group_num+=1
                        obj.vertex_groups.remove(group)
    
        self.report({'INFO'}, f"Vertex group '{group_num}' cleared from selected objects")
        return {'FINISHED'}




class FixVertexGroup(bpy.types.Operator):
    bl_idname = "spine.fix_vertex_group"
    bl_label = "Fix Vertex Group"
    bl_description = "Fix"

    #group_name: bpy.props.StringProperty(name="Group Name", default="Group_Name")

    def execute(self, context):
        selected_objects = context.selected_objects
        bone_list=[]
        group_new=0
        group_add=0
        selected_objects = context.selected_objects

        for obj in selected_objects:
            if obj.type == 'MESH':
                # 获取所有顶点组
                vertex_groups = obj.vertex_groups
                vertices= obj.data.vertices
                # 如果有顶点组
                if vertex_groups:
                    for vertex in vertices:
                        has_weight = 0
                        for vgroup in vertex_groups:
                            # 获取该顶点在该顶点组中的权重
                            weight = None
                            try:
                                weight = vgroup.weight(vertex.index)
                            except RuntimeError:
                                # 顶点不在此顶点组中
                                weight = 0.0

                            if weight > 0:
                                has_weight = 1
                                break
                        if has_weight == 0:
                            group_exists = False
                            group_name = "root"
                            root_group = 0
                            for vgroup in obj.vertex_groups:
                                if vgroup.name == group_name:
                                    group_exists = True
                                    root_group = vgroup
                                    #print(f"顶点组 '{group_name}' 已经存在。")
                                    break
                            group_add+=1
                            if group_exists:
                                root_group.add([vertex.index], 1.0, 'REPLACE')
                            else:
                                root_group = obj.vertex_groups.new(name=group_name)
                                root_group.add([vertex.index], 1.0, 'REPLACE')

                else:
                    root_group = obj.vertex_groups.new(name="root")
                    group_new+=1
                    # 给每个顶点赋予权重 1
                    for vertex in vertices:
                        root_group.add([vertex.index], 1.0, 'REPLACE')
            else:
                print("请确保选中的对象是一个网格对象。")
        self.report({'INFO'}, f"Vertex group add'{group_add}' new {group_new}")
        return {'FINISHED'}


class FixWeight(bpy.types.Operator):
    bl_idname = "spine.fix_weight"
    bl_label = "Fix Weight"
    bl_description = "Fix Weight"

    def execute(self, context):
        choose_num=0
        selected_objects = bpy.context.selected_objects
        for obj in selected_objects:
            if obj.type == 'MESH':
                choose_num+=1
                #normalize_and_round_vertex_weights(obj)
                mesh = obj.data
        
                # 获取所有顶点组
                vertex_groups = obj.vertex_groups
                
                # 遍历每个顶点
                for vertex in mesh.vertices:
                    total_weight = sum([group.weight for group in vertex.groups])
                    group_len = len(vertex.groups)
                    if total_weight > 0:
                        for group in vertex.groups:
                            # 归一化权重
                            normalized_weight = group.weight / total_weight
                            # 四舍五入保留小数点后2位
                            rounded_weight = round(normalized_weight, 1)
                            vertex_groups[group.group].add([vertex.index], rounded_weight, 'REPLACE')
                            if group_len>1 and rounded_weight==0:
                                vertex_groups[group.group].remove([vertex.index])
        self.report({'INFO'}, f"修改了 '{choose_num}' 个物体")
        return {'FINISHED'}


class ChooseVertexGroup(bpy.types.Operator):
    bl_idname = "spine.choose_vertex_group"
    bl_label = "Fix Vertex Group"
    bl_description = "Fix"

    def execute(self, context):
        choose_num=0
        group_name = "root"
        bpy.ops.object.select_all(action='DESELECT')
        for obj in bpy.context.scene.objects:

            if obj.type == 'MESH':

                for vgroup in obj.vertex_groups:
                    if vgroup.name == group_name:
                        choose_num+=1
                        obj.select_set(True)
                        #print(f"对象 '{obj.name}' 包含顶点组 '{group_name}'，已选中。")
                        break
        if bpy.context.selected_objects:
            bpy.context.view_layer.objects.active = bpy.context.selected_objects[-1]
        self.report({'INFO'}, f"选中了 '{choose_num}' 个物体")
        return {'FINISHED'}


class ApplyAnmiScale(bpy.types.Operator):
    bl_idname = "spine.apply_anmi_scale"
    bl_label = "Apply Anmi Scale"
    bl_description = "Anmi Scale"

    def execute(self, context):
        armature_obj = bpy.context.active_object  # 获取当前活动对象（应为骨骼对象）
        scale_factor = armature_obj.scale.x  # 设定缩放因子（例如，2倍缩放）
        # 检查是否为骨骼对象
        if armature_obj.type != 'ARMATURE':
            print(f"{armature_obj.name} is not an armature object.")
            return

        # 获取骨骼对象的动画数据
        anim_data = armature_obj.animation_data

        if not anim_data or not anim_data.action:
            print(f"{armature_obj.name} has no animation data.")
            return

        action = anim_data.action

        # 遍历动作中的所有F曲线
        for fcurve in action.fcurves:
            # 只处理位置相关的F曲线（location_x, location_y, location_z）
            if fcurve.data_path.endswith(("location")):
                for keyframe in fcurve.keyframe_points:
                    # 对关键帧的位置值进行缩放
                    keyframe.co.y *= scale_factor
                    keyframe.handle_left.y *= scale_factor
                    keyframe.handle_right.y *= scale_factor
        self.report({'INFO'}, f"应用了 '{scale_factor}' 倍缩放")
        return {'FINISHED'}




class SpineUIPanel(bpy.types.Panel):
    #bl_idname = 'my.blblop1ui'
    bl_label = "File"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SToB'
    

        
    def draw(self, context):
        self.layout.label(text="Import:", icon="IMPORT")
        row = self.layout.row(align=True)
        #row.operator("object.select_all(action='TOGGLE')", icon="RENDER_ANIMATION", text="Load anim ...")
        row.operator("spine.import_json", icon="MESH_CUBE", text="加载JSON ...")

        row4 = self.layout.row(align=True)
        #row.operator("object.select_all(action='TOGGLE')", icon="RENDER_ANIMATION", text="Load anim ...")
        row4.operator("spine.add_json", icon="MESH_CUBE", text="追加JSON ...")

        row6 = self.layout.row(align=True)
        # row.operator("object.select_all(action='TOGGLE')", icon="RENDER_ANIMATION", text="Load anim ...")
        row6.operator("spine.reload_json", icon="MESH_CUBE", text="重载材质 ...")

        self.layout.label(text="tools:", icon="IMPORT")
        row1 = self.layout.row(align=True)
        #row.operator("object.select_all(action='TOGGLE')", icon="RENDER_ANIMATION", text="Load anim ...")
        row1.operator("spine.clear_vertex_group", icon="MESH_CUBE", text="删除无效顶点组")
        row2 = self.layout.row(align=True)
        #row.operator("object.select_all(action='TOGGLE')", icon="RENDER_ANIMATION", text="Load anim ...")
        row2.operator("spine.fix_vertex_group", icon="MESH_CUBE", text="补全空顶点组")
        row3 = self.layout.row(align=True)
        #row.operator("object.select_all(action='TOGGLE')", icon="RENDER_ANIMATION", text="Load anim ...")
        row3.operator("spine.choose_vertex_group", icon="MESH_CUBE", text="选择包含root组的物体")
        row5 = self.layout.row(align=True)
        #row.operator("object.select_all(action='TOGGLE')", icon="RENDER_ANIMATION", text="Load anim ...")
        row5.operator("spine.fix_weight", icon="MESH_CUBE", text="权重归一")

        row7 = self.layout.row(align=True)
        # row.operator("object.select_all(action='TOGGLE')", icon="RENDER_ANIMATION", text="Load anim ...")
        row7.operator("spine.apply_anmi_scale", icon="MESH_CUBE", text="应用骨骼动画缩放")





def register():
    bpy.utils.register_class(ImportJsonOperator)
    bpy.utils.register_class(AddJsonOperator)
    bpy.utils.register_class(ReloadJsonOperator)
    bpy.utils.register_class(ApplyAnmiScale)


    bpy.utils.register_class(FixWeight)
    bpy.utils.register_class(ClearVertexGroup)
    bpy.utils.register_class(FixVertexGroup)
    bpy.utils.register_class(ChooseVertexGroup)
    bpy.utils.register_class(SpineUIPanel)


def unregister():
    bpy.utils.register_class(FixWeight)
    bpy.utils.register_class(ImportJsonOperator)
    bpy.utils.register_class(AddJsonOperator)
    bpy.utils.register_class(ReloadJsonOperator)
    bpy.utils.register_class(ApplyAnmiScale)
    bpy.utils.register_class(ClearVertexGroup)
    bpy.utils.register_class(FixVertexGroup)
    bpy.utils.register_class(ChooseVertexGroup)
    bpy.utils.register_class(SpineUIPanel)

    
    

#if __name__ == "__main__":
    #register()
