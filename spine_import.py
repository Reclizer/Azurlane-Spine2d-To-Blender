import bpy
import time
import json
from mathutils import Vector, Matrix, Quaternion
import math
import os
import numpy as np

def convert_to_latin1_compatible(text):
    def is_latin1(character):
        try:
            character.encode('latin-1')
            return True
        except UnicodeEncodeError:
            return False

    return ''.join([f'u{ord(char):04x}' if not is_latin1(char) else char for char in text])


def get_vertices_list(_vertices, scale=1, _list=[]):
    _data = []

    for _ in range(_vertices.pop(0)):
        _data.append(
            {
                'bone_idx': _vertices.pop(0),
                'x': _vertices.pop(0) * scale,
                'y': _vertices.pop(0) * scale,
                'weight': _vertices.pop(0),
            }
        )
    _list.append(_data)
    if len(_vertices) >= 5:
        return get_vertices_list(_vertices, scale=scale, _list=_list)
    return _list

def create_materials(name, image_path):
    # 创建新的材质
    material = bpy.data.materials.new(name=name)
    material["shader"] = "PdxMeshPortrait"

    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    # 清空默认节点
    for node in nodes:
        nodes.remove(node)

    # 创建材质输出节点
    material_output = nodes.new(type='ShaderNodeOutputMaterial')
    material_output.location = (300, 0)

    # 创建 Principled BSDF 节点
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)

    # 创建图像纹理节点
    texture_image = nodes.new(type='ShaderNodeTexImage')
    texture_image.image = bpy.data.images.load(image_path)
    texture_image.location = (-300, 0)

    # 将节点连接起来
    links.new(texture_image.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], material_output.inputs['Surface'])
    links.new(texture_image.outputs['Alpha'], bsdf.inputs['Alpha'])
    #material.blend_method = 'CLIP'
    material.blend_method = 'HASHED'

    return material

def _get_bone_matrix_dict(arm_obj):
    _matrix_dict = {}
    for i in arm_obj.pose.bones:
        _dict = {
            "matrix_eular": i.matrix.to_euler('XYZ').copy(),
            "matrix_scale": i.matrix.to_scale().copy(),
            "matrix_translation": i.matrix.to_translation().copy(),
        }
        _matrix_dict |= {i.name: _dict}
    return _matrix_dict

def get_uv_loc(data):
    rotate = data.get("rotate").strip()
    xy = data.get("xy").strip()
    size = data.get("size").strip()
    orig = data.get("orig").strip()
    offset = data.get("offset").strip()

    width, height = list(map(int, size.split(",")))
    ltx, lty = list(map(int, xy.split(",")))
    origx, origy = list(map(int, orig.split(",")))
    offset_x, offset_y = list(map(int, offset.split(",")))

    offset_x = offset_x
    offset_y = origy - height - offset_y

    if rotate == "true":
        final_x0 = ltx - offset_y
        final_y0 = lty - (origx - width) + offset_x
        final_x = final_x0 + origy
        final_y = final_y0 + origx
    else:
        final_x0 = ltx - offset_x
        final_y0 = lty - offset_y
        final_x = final_x0 + origx
        final_y = final_y0 + origy

    return (final_x0, final_y0, final_x, final_y)

def create_uv(mesh_name, uvs, atlas):
    width = atlas.get("size")[0]
    height = atlas.get("size")[1]

    if not atlas.get(mesh_name):
        return None

    loc = get_uv_loc(atlas[mesh_name])

    x0, y0, x1, y1 = loc[0], loc[1], loc[2], loc[3]

    # if mesh_name=="hair_B":
    # print(x0,y0,x1,y1)

    uv_list = []
    u0, u1, v0, v1 = x0 / width, x1 / width, y0 / height, y1 / height
    # =============================================================================
    if atlas[mesh_name].get("rotate") == "true":
        # u0,u1,v0,v1=x0/width,x1/width,y0/height,y1/height
        for i in range(int(len(uvs) / 2)):
            u = u0 + (u1 - u0) * (uvs[i * 2 + 1])
            v = 1 - v1 + (v1 - v0) * (uvs[i * 2])
            uv_list.append((u, v))
    else:
        # u0,u1,v0,v1=x0/width,x1/width,y0/height,y1/height
        for i in range(int(len(uvs) / 2)):
            u = u0 + (u1 - u0) * (uvs[i * 2])
            v = 1 - v1 + (v1 - v0) * (1 - uvs[i * 2 + 1])
            uv_list.append((u, v))
    # =============================================================================

    return uv_list

def read_atlas(file_path):
    atlas = {}
    with open(file_path, 'r', encoding='utf-8') as file:
        index = -1
        num = 0
        list_name = ""
        list_0 = {}
        for line in file:
            index += 1
            if index == 1:
                atlas["image"] = line.strip()
            if index == 2:
                size = line.split(":")[1].strip().split(",")
                atlas["size"] = (int(size[0]), int(size[1]))
            if index == 3:
                atlas["format"] = line.split(":")[1].strip()
            if index == 4:
                atlas["filter"] = line.split(":")[1].strip()
            if index == 5:
                atlas["repeat"] = line.split(":")[1].strip()
            if index > 5:
                num += 1
                if num == 1:
                    list_name = line.strip()
                if num == 2:
                    list_0["rotate"] = line.split(":")[1].strip()
                if num == 3:
                    list_0["xy"] = line.split(":")[1].strip()
                if num == 4:
                    list_0["size"] = line.split(":")[1].strip()
                if num == 5:
                    list_0["orig"] = line.split(":")[1].strip()
                if num == 6:
                    list_0["offset"] = line.split(":")[1].strip()
                if num == 7:
                    list_0["index"] = int(line.split(":")[1].strip())
                    atlas[list_name] = list_0
                    list_0 = {}
                    num = 0

    return atlas


def create_bones(rig_name, bones_info, scale):
    tmp_rig_name = rig_name
    armt = bpy.data.armatures.new("armature")
    armt.name = "imported_armature"
    armt.display_type = "STICK"


    # create the object and link to the scene
    new_rig = bpy.data.objects.new(tmp_rig_name, armt)
    bpy.context.scene.collection.objects.link(new_rig)
    bpy.context.view_layer.objects.active = new_rig
    new_rig.show_in_front = True
    new_rig.select_set(state=True)

    bpy.ops.object.mode_set(mode="EDIT")
    bone_dict = {}
    bones_info_xy = bones_info.copy()

    for bone in bones_info_xy:
        bone_name = bone["name"]
        parent_name = bone.get("parent")
        length = bone.get("length", 1) * scale
        transform = bone.get('transform')
        new_bone = armt.edit_bones.new(name=bone["name"])
        new_bone.select = True
        bone_dict[bone["name"]] = new_bone
        if parent_name:
            parent_bone = bone_dict[bone["parent"]]
            new_bone.parent = parent_bone
            new_bone.head = parent_bone.head
            new_bone.use_connect = False
        else:
            new_bone.head = Vector((0, 0, 0))

        if length == 1 * scale:
            # new_bone.tail = new_bone.head + Vector((0, length, 0))
            new_bone.tail = new_bone.head + Vector((length * 0.01, 0, 0))
        else:
            new_bone.tail = new_bone.head + Vector((length, 0, 0))
        if transform == "noRotationOrReflection":
            new_bone.use_inherit_rotation = False


    # 变换骨骼
    bpy.ops.object.mode_set(mode='POSE')
    for bone in bones_info:
        bone_name = bone["name"]
        rotation = bone.get("rotation", 0)
        x = bone.get("x", 0) * scale
        y = bone.get("y", 0) * scale
        bone_c = new_rig.pose.bones[bone["name"]]
        bone_c.location = 0, x, y
        transform = bone.get('transform')
        #if transform == "noRotationOrReflection":
            #armt.bones[bone_name].use_inherit_rotation = False
            #rotation=0
        bone_c.rotation_mode = 'XYZ'
        bone_c.rotation_euler[0] = math.radians(rotation)

    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    return new_rig


# 函数：获取或创建顶点组
def get_or_create_vertex_group(obj, group_name):
    if group_name in obj.vertex_groups:
        vertex_group = obj.vertex_groups[group_name]
    else:
        vertex_group = obj.vertex_groups.new(name=group_name)
    return vertex_group


def create_mesh(mesh_name, bone_name, point_data, bone_list,  atlas,  bone_matrix, scale):
    if not point_data.get('type') == 'mesh':
        width = point_data.get('width', 0) * scale
        height = point_data.get('height', 0) * scale
        mesh_rot = point_data.get('rotation', 0)
        x = point_data.get('x',0) * scale
        y = point_data.get('y',0) * scale
        _bone=bone_matrix.get(bone_name)

        region_x = x * math.cos(_bone['matrix_eular'][0]) - y * math.sin(_bone['matrix_eular'][0])
        region_y = x * math.sin(_bone['matrix_eular'][0]) + y * math.cos(_bone['matrix_eular'][0])
        rotate = _bone['matrix_eular'][0] + math.radians(mesh_rot)

        mesh_vertices = [
            (
                (
                        (-width / 2) * math.cos(rotate) - (height / 2) * math.sin(rotate) + region_x)
                * _bone['matrix_scale'][1] + _bone['matrix_translation'][0],
                0,
                (
                        (-width / 2) * math.sin(rotate) + (height / 2) * math.cos(rotate) + region_y)
                * _bone['matrix_scale'][2] + _bone['matrix_translation'][2]
            ), (
                (
                        (width / 2) * math.cos(rotate) - (height / 2) * math.sin(rotate) + region_x)
                * _bone['matrix_scale'][1] + _bone['matrix_translation'][0],
                0,
                (
                        (width / 2) * math.sin(rotate) + (height / 2) * math.cos(rotate) + region_y)
                * _bone['matrix_scale'][2] + _bone['matrix_translation'][2]
            ), (
                (
                        (-width / 2) * math.cos(rotate) - (-height / 2) * math.sin(rotate) + region_x)
                * _bone['matrix_scale'][1] + _bone['matrix_translation'][0],
                0,
                (
                        (-width / 2) * math.sin(rotate) + (-height / 2) * math.cos(rotate) + region_y)
                * _bone['matrix_scale'][2] + _bone['matrix_translation'][2]
            ), (
                (
                        (width / 2) * math.cos(rotate) - (-height / 2) * math.sin(rotate) + region_x)
                * _bone['matrix_scale'][1] + _bone['matrix_translation'][0],
                0,
                (
                        (width / 2) * math.sin(rotate) + (-height / 2) * math.cos(rotate) + region_y)
                * _bone['matrix_scale'][2] + _bone['matrix_translation'][2]
            )
        ]

        face_list = [[0, 1, 3, 2]]

        vertices_list =mesh_vertices
        uvs = [0, 0, 1, 0, 0, 1, 1, 1]

        mesh = bpy.data.meshes.new(mesh_name)
        mesh_obj = bpy.data.objects.new(mesh_name, mesh)
        mesh.from_pydata(mesh_vertices, [], face_list)
        mesh.update()
        scene = bpy.context.scene
        scene.collection.objects.link(mesh_obj)


        for i in range(len(vertices_list)):
            #if()
            vertex_group = get_or_create_vertex_group(mesh_obj, bone_name)
            vertex_group.add([i], 1, 'REPLACE')

        uv_list = create_uv(mesh_name, uvs, atlas)
        if not uv_list is None:
            if len(uv_list) == len(vertices_list):
                uv_layer = mesh.uv_layers.new()
                for face in mesh.polygons:
                    for loop_index in face.loop_indices:
                        vertex_index = mesh.loops[loop_index].vertex_index
                        uv_layer.data[loop_index].uv = uv_list[vertex_index]

        return mesh_obj

    if point_data.get('type') == 'mesh':
        has_weight=False
        #print("====================")

        #print("----------")
        vertices = point_data.get('vertices')
        edges = point_data.get('edges')
        triangles = point_data.get('triangles')
        uvs = point_data.get('uvs')
        #print(vertices)

        edge_list = []
        for i in range(int(len(edges) / 2)):
            edge_list.append((int(edges[i * 2] / 2), int(edges[i * 2 + 1] / 2)))

        face_list = []
        for i in range(int(len(triangles) / 3)):
            face_list.append((triangles[i * 3], triangles[i * 3 + 1], triangles[i * 3 + 2]))

        mesh_vertices=[]
        if len(vertices) == len(set(triangles)) * 2:
            _bone = bone_matrix.get(bone_name)
            vertices_list = [(vertices[i:i + 2]) for i in range(0, len(vertices), 2)]

            for x, y in vertices_list:
                x *= scale
                y *= scale
                weight = 1
                pos = [
                    (x * math.cos(_bone['matrix_eular'][0]) - y * math.sin(_bone['matrix_eular'][0]))
                    * _bone['matrix_scale'][1] + _bone['matrix_translation'][0] * weight,

                    0,

                    (y * math.cos(_bone['matrix_eular'][0]) + x * math.sin(_bone['matrix_eular'][0]))
                    * _bone['matrix_scale'][1] + _bone['matrix_translation'][2] * weight,
                ]
                mesh_vertices.append(Vector(pos))
        else:
            has_weight=True
            vertices_list = get_vertices_list(vertices, scale=scale, _list=[])
            for data in vertices_list:
                x = y = 0

                for i in data:
                    bone_index = i.get('bone_idx')
                    if bone_index:
                        _bone = bone_matrix.get(bone_list[bone_index].get("name"))
                        x += (
                                     (i['x'] * math.cos(_bone['matrix_eular'][0]) - i['y'] * math.sin(
                                         _bone['matrix_eular'][0]))
                                     * _bone['matrix_scale'][1] + _bone['matrix_translation'][0]
                             ) * i['weight']

                        y += (
                                     (i['y'] * math.cos(_bone['matrix_eular'][0]) + i['x'] * math.sin(
                                         _bone['matrix_eular'][0]))
                                     * _bone['matrix_scale'][1] + _bone['matrix_translation'][2]
                             ) * i['weight']
                    else:
                        x += i['x']
                        y += i['y']

                pos = [x, 0, y]
                mesh_vertices.append(Vector(pos))




        mesh = bpy.data.meshes.new(mesh_name)
        mesh_obj = bpy.data.objects.new(mesh_name, mesh)
        mesh.from_pydata(mesh_vertices, edge_list, face_list)
        mesh.update()
        scene = bpy.context.scene
        scene.collection.objects.link(mesh_obj)

        uv_list = create_uv(mesh_name, uvs, atlas)

        if not uv_list is None:
            if len(uv_list) == len(vertices_list):
                uv_layer = mesh.uv_layers.new()
                for face in mesh.polygons:
                    for loop_index in face.loop_indices:
                        vertex_index = mesh.loops[loop_index].vertex_index
                        uv_layer.data[loop_index].uv = uv_list[vertex_index]


        vert_weight = []
        if has_weight:
            for i in range(len(vertices_list)):
                weight_list=vertices_list[i]

                for w in weight_list:
                    b_name=bone_list[w.get('bone_idx')].get("name")
                    w_num=w.get('weight')
                    vertex_group = get_or_create_vertex_group(mesh_obj, b_name)
                    vertex_group.add([i], w_num, 'REPLACE')
        else:
            for i in range(len(vertices_list)):
                vertex_group = get_or_create_vertex_group(mesh_obj, bone_name)
                vertex_group.add([i], 1, 'REPLACE')


        return mesh_obj


    return None


def extend_image(image, new_width, new_height):
    """Extend the image to a new width and height, filling with transparency."""
    old_width, old_height = image.size
    new_image = bpy.data.images.new(image.name + "_extended", width=new_width, height=new_height, alpha=True)

    # Initialize new image with transparent pixels
    new_pixels = np.zeros((new_height, new_width, 4), dtype=np.float32)

    # Load the original image pixels and reshape
    original_pixels = np.array(image.pixels[:]).reshape((old_height, old_width, 4))

    # Copy the original pixels into the new image (top-left aligned)
    new_pixels[:old_height, :old_width, :] = original_pixels

    # Flatten the array and assign to the new image
    new_image.pixels = new_pixels.flatten().tolist()

    return new_image

def create_new_image(image1,image2):
    """Combine two images vertically, preserving transparency."""
    # Get image sizes
    width1, height1 = image1.size
    width2, height2 = image2.size

    # Ensure the widths are the same
    #if width1 != width2:
        #raise ValueError("The widths of the images must be the same to combine them vertically.")

    # Determine the maximum width
    max_width = max(width1, width2)
    # Extend both images to the same width
    # Extend both images to the same width
    if width1 < max_width:
        image1 = extend_image(image1, max_width, height1)
    if width2 < max_width:
        image2 = extend_image(image2, max_width, height2)

    # Create a new image with combined height
    combined_height = height1 + height2
    combined_image = bpy.data.images.new("CombinedImage", width=max_width, height=combined_height, alpha=True)

    # Convert image pixel data to numpy arrays
    image1_pixels = np.array(image1.pixels[:]).reshape((height1, max_width, 4))
    image2_pixels = np.array(image2.pixels[:]).reshape((height2, max_width, 4))

    # Create a new array for the combined image
    combined_pixels = np.zeros((combined_height, max_width, 4), dtype=np.float32)

    # Copy pixel data into the combined array
    combined_pixels[:height1, :, :] = image1_pixels
    combined_pixels[height1:, :, :] = image2_pixels

    # Flatten the array and assign it to the combined image
    combined_image.pixels = combined_pixels.flatten().tolist()

    return combined_image

def change_texture_path(obj, new_image_path):
    if obj.type == 'MESH':
        for mat in obj.data.materials:
            if mat.use_nodes:
                # 遍历材质节点
                for node in mat.node_tree.nodes:
                    # 查找图像纹理节点
                    if node.type == 'TEX_IMAGE':
                        # 更改图像路径
                        node.image.filepath = new_image_path
                        #print(f"Texture path for {obj.name} changed to {new_image_path}")


def create_mesh_all(json_data, atlas, rig, image_path, bone_matrix, scale,add):
    final_image=image_path
    max_meshindex = 0
    image1=""
    image2 =""
    if add:

        oldimg_path = ""

        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                meshindex = obj.data.get("meshindex")
                if meshindex and meshindex > max_meshindex:
                    max_meshindex = meshindex
                    # 遍历对象的所有材质
                    for mat in obj.data.materials:
                        # 确保材质使用节点
                        if mat.use_nodes:
                            for node in mat.node_tree.nodes:
                                # 找到纹理图像节点
                                if node.type == 'TEX_IMAGE':
                                    image = node.image
                                    if image:
                                        oldimg_path = image.filepath
        max_meshindex+=1
        if oldimg_path != "":

            image1_path = oldimg_path
            image2_path = image_path
            final_image = image_path.split(".")[0] + "_all" + ".png"

            # Load images
            image1 = bpy.data.images.load(image1_path)
            image2 = bpy.data.images.load(image2_path)
            width1, height1 = image1.size
            width2, height2 = image2.size
            # Combine images
            combined_image = create_new_image(image1, image2)
            combined_image.filepath_raw = final_image
            combined_image.file_format = 'PNG'
            combined_image.save()



            h_scale = height1 / (height1 + height2)

            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    meshindex = obj.data.get("meshindex")
                    if meshindex:
                        change_texture_path(obj,final_image)
                        uv_layer = obj.data.uv_layers.active
                        # 调整UV坐标
                        for poly in obj.data.polygons:
                            for loop_index in poly.loop_indices:
                                uv = uv_layer.data[loop_index].uv
                                # 缩放UV的Y坐标
                                if width1 < width2:
                                    uv.x *= width1 / width2
                                uv.y *= h_scale



    bones_info = json_data.get("bones")
    # 读取所有插槽,不在插槽内的需要隐藏
    slots = json_data.get("slots")
    bone_list = json_data.get("bones")
    bone_info={}
    attachment_list = {}
    bone_z = {}
    mesh_index = {}
    z_add = 0-(0.05*(max_meshindex+1))
    mesh_index_add = max_meshindex
    for slot in slots:
        z_add -= 0.05
        bone = slot.get('bone')
        attachment = slot.get('attachment')
        bone_info[slot.get('name')] = bone
        bone_z[slot.get('name')] = z_add
        mesh_index[slot.get('name')] = mesh_index_add
        mesh_index_add += 1

        if attachment:
            attachment_list[slot.get('name')] = attachment
    mesh_date = json_data.get("skins")[0].get("attachments")
    # 遍历所有skin,并隐藏不在附件中的网格

    material = create_materials(f'PDXmat_All', final_image)
    for key, value in mesh_date.items():
        bone_name=bone_info.get(key)
        for mesh_name, point_data in value.items():
            attachment = attachment_list.get(key)
            obj = create_mesh(mesh_name, bone_name, point_data, bone_list, atlas, bone_matrix, scale)
            if not attachment:
                obj.hide_viewport = True
                obj.hide_render = True
            else:
                if attachment != mesh_name:
                    obj.hide_viewport = True
                    obj.hide_render = True
            if obj:
                obj.location.y += bone_z[key]
                obj.data["meshindex"] = mesh_index[key]
                #material = create_materials(f'PDXmat_{mesh_name}', final_image)

                modifier = obj.modifiers.new(name="Armature", type='ARMATURE')
                modifier.object = rig
                modifier.use_vertex_groups = True

                if add:
                    width1, height1=image1.size
                    width2, height2=image2.size
                    uv_layer = obj.data.uv_layers.active
                    h_scale=height2/(height2+height1)
                    h_scale_add=height1/(height2+height1)
                    # 调整UV坐标
                    for poly in obj.data.polygons:
                        for loop_index in poly.loop_indices:
                            uv = uv_layer.data[loop_index].uv
                            # 缩放UV的Y坐标
                            if width2 < width1:
                                w_scale=width2/width1
                                uv.x *= w_scale
                            uv.y *= h_scale
                            uv.y +=h_scale_add


                bpy.context.view_layer.update()
                # 检查对象是否已经有材质槽
                if obj.data.materials:
                    # 将新创建的材质赋予第一个材质槽
                    obj.data.materials[0] = material
                else:
                    # 如果没有材质槽，则追加材质
                    obj.data.materials.append(material)


def set_constant_interpolation_current_frame():
    # 获取当前帧
    current_frame = bpy.context.scene.frame_current

    # 获取所有对象
    for obj in bpy.context.scene.objects:
        # 确保对象有动画数据
        if obj.animation_data and obj.animation_data.action:
            action = obj.animation_data.action

            # 遍历动作中的所有动画曲线
            for fcurve in action.fcurves:
                # 查找当前帧的关键帧点
                for keyframe in fcurve.keyframe_points:
                    if keyframe.co[0] == current_frame:
                        keyframe.interpolation = 'CONSTANT'

def create_animations(animations_data, rig, scale):
    animations = animations_data.get("normal")
    frame_end = 0
    if animations:
        bone_anim = animations.get("bones")
        event = animations.get("events")
        if event:
            for e in event:
                name = e.get("name")
                if name == "finish":
                    frame_end = int(e.get("time") * 30)
    else:
        for key,value in animations_data.items():
            if "bones" in value:
                bone_anim = value.get("bones")
                break







    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')

    #bpy.context.scene.frame_end = frame_end

    for bone_key, value in bone_anim.items():
        bone_name = bone_key
        rotate = value.get("rotate")
        translate = value.get("translate")


        if rotate:
            rot = 0
            for key in rotate:
                frame = int(key.get("time", 0) * 30)
                if frame>frame_end:
                    frame_end=frame

                bpy.context.scene.frame_set(frame)
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.ops.object.select_pattern(pattern=bone_name)
                key_r = key.get("angle", 0) + rot

                curve = key.get("curve","")

                if curve=="stepped":
                    set_constant_interpolation_current_frame()

                rot -= key_r

                angle_radians = math.radians(key_r)
                bpy.ops.transform.rotate(
                    value=angle_radians,
                    orient_axis='Y')

                bpy.ops.anim.keyframe_insert_by_name(type="Rotation")

        if translate:
            loc = 0
            loc_x = 0
            for key in translate:
                frame = int(key.get("time", 0) * 30)
                bpy.context.scene.frame_set(frame)
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.ops.object.select_pattern(pattern=bone_name)

                key_y = key.get("y", 0) * scale + loc
                loc -= key_y
                key_x = key.get("x", 0) * scale + loc_x
                loc_x -= key_x

                bpy.ops.transform.translate(value=(key_x, 0, key_y), orient_axis_ortho='Z')
                bpy.ops.anim.keyframe_insert_by_name(type="Location")
    bpy.context.scene.frame_end = frame_end
    # 遍历对象的所有动作
    for action in bpy.data.actions:
        # 遍历每个动作中的所有F曲线
        for fcurve in action.fcurves:
            # 遍历F曲线中的所有关键帧点
            for keyframe_point in fcurve.keyframe_points:
                keyframe_point.interpolation = 'LINEAR'





def import_jsonfile(json_path,add=False,reload=False):
    scale = 0.01

    name = os.path.basename(json_path)
    folder_path = os.path.dirname(json_path)
    atlas_path = folder_path + "/" + name.split(".")[0] + ".atlas"
    # 把图集转化json可读
    atlas = read_atlas(atlas_path)
    # 图片路径
    image_path = folder_path + "/" + atlas.get("image")
    #image_path = image_path.split(".")[0] + ".png"
    # 动画

    # 解析spine数据
    with open(json_path, 'r', encoding='utf-8') as file:
        content = file.read()


    processed_content = convert_to_latin1_compatible(content)
    json_data = json.loads(processed_content)

    if reload:


        mesh_date = json_data.get("skins")[0].get("attachments")
        mesh_uv={}
        for key, value in mesh_date.items():
            #bone_name = bone_info.get(key)
            for mesh_name, point_data in value.items():
                if point_data.get('type') == 'mesh':
                    uvs = point_data.get('uvs')
                    uv_list = create_uv(mesh_name, uvs, atlas)
                else:
                    uvs = [0, 0, 1, 0, 0, 1, 1, 1]
                    uv_list = create_uv(mesh_name, uvs, atlas)
                if not uv_list is None:
                    mesh_uv[mesh_name]=uv_list
        for obj in bpy.data.objects:
            mesh = obj.data
            if obj.type == 'MESH':
                if obj.name in mesh_uv:
                    vertices = [v.co for v in mesh.vertices]
                    uv_list=mesh_uv[obj.name]

                    if len(uv_list) == len(vertices):
                        if mesh.uv_layers.active:
                            uv_layer = mesh.uv_layers.active
                            mesh.uv_layers.remove(uv_layer)

                            uv_layer = mesh.uv_layers.new()
                            for face in mesh.polygons:
                                for loop_index in face.loop_indices:
                                    vertex_index = mesh.loops[loop_index].vertex_index
                                    uv_layer.data[loop_index].uv = uv_list[vertex_index]
                change_texture_path(obj,image_path)




    else:
        # 创建材质
        # image_path
        # materials=creat_materials(atlas["image"].split(".")[0]+"_mat",image_path)
        # 创建骨骼
        bones_info = json_data.get("bones")
        rig_name = name.split(".")[0] + "_rig"
        new_rig = create_bones(rig_name, bones_info, scale)
        bone_matrix = _get_bone_matrix_dict(new_rig)

        create_mesh_all(json_data, atlas, new_rig, image_path, bone_matrix, scale, add)

        animations = json_data.get("animations")

        if not add:
            create_animations(animations, new_rig, scale)




    ''''''