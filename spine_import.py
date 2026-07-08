import bpy
import json
import math
import os
import numpy as np
from mathutils import Vector

# spine 动画时间以秒为单位, 按 30fps 换算成帧号
FPS = 30


def convert_to_latin1_compatible(text):
    """把 json 里 latin-1 无法表示的字符(如中文)转成 uXXXX 形式, 避免骨骼/顶点组名乱码"""
    if all(ord(char) < 256 for char in text):
        return text
    return ''.join(char if ord(char) < 256 else f'u{ord(char):04x}' for char in text)


def get_vertices_list(vertices, scale=1):
    """解析加权网格的顶点数据

    数据格式: [骨骼数, (骨骼索引, x, y, 权重) * 骨骼数, 骨骼数, ...]
    返回: 每个顶点一个 list, 内含它受影响的所有骨骼信息
    """
    result = []
    i = 0
    total = len(vertices)
    while i < total:
        bone_count = int(vertices[i])
        i += 1
        influences = []
        for _ in range(bone_count):
            influences.append({
                'bone_idx': int(vertices[i]),
                'x': vertices[i + 1] * scale,
                'y': vertices[i + 2] * scale,
                'weight': vertices[i + 3],
            })
            i += 4
        result.append(influences)
    return result


def create_materials(name, image_path):
    material = bpy.data.materials.new(name=name)
    material["shader"] = "PdxMeshPortrait"

    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    material_output = nodes.new(type='ShaderNodeOutputMaterial')
    material_output.location = (300, 0)

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)

    texture_image = nodes.new(type='ShaderNodeTexImage')
    texture_image.image = bpy.data.images.load(image_path)
    texture_image.location = (-300, 0)

    links.new(texture_image.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], material_output.inputs['Surface'])
    links.new(texture_image.outputs['Alpha'], bsdf.inputs['Alpha'])
    material.blend_method = 'HASHED'

    return material


def _get_bone_matrix_dict(arm_obj):
    _matrix_dict = {}
    for pbone in arm_obj.pose.bones:
        _matrix_dict[pbone.name] = {
            "matrix_eular": pbone.matrix.to_euler('XYZ').copy(),
            "matrix_scale": pbone.matrix.to_scale().copy(),
            "matrix_translation": pbone.matrix.to_translation().copy(),
        }
    return _matrix_dict


def get_uv_loc(data):
    """由图集条目算出贴图区域在整张图上的像素范围 (x0, y0, x1, y1)"""
    rotate = data.get("rotate", "false")
    width, height = (int(v) for v in data["size"].split(","))
    ltx, lty = (int(v) for v in data["xy"].split(","))
    origx, origy = (int(v) for v in data["orig"].split(","))
    offset_x, offset_y = (int(v) for v in data["offset"].split(","))

    offset_y = origy - height - offset_y

    if rotate in ("true", "270"):
        final_x0 = ltx - offset_y
        final_y0 = lty - (origx - width) + offset_x
        return (final_x0, final_y0, final_x0 + origy, final_y0 + origx)

    # false / 180
    final_x0 = ltx - offset_x
    final_y0 = lty - offset_y
    return (final_x0, final_y0, final_x0 + origx, final_y0 + origy)


def create_uv(region_name, uvs, atlas):
    """把 spine 的 uv 坐标映射到整张图集上, 找不到图集条目时返回 None"""
    region = atlas.get(region_name)
    if not region:
        return None

    width, height = atlas["size"]
    x0, y0, x1, y1 = get_uv_loc(region)
    u0, u1, v0, v1 = x0 / width, x1 / width, y0 / height, y1 / height
    rotate = region.get("rotate", "false")

    uv_list = []
    for i in range(len(uvs) // 2):
        su, sv = uvs[i * 2], uvs[i * 2 + 1]
        if rotate == "true":
            ut, vt = sv, su
        elif rotate == "180":
            ut, vt = 1 - su, sv
        elif rotate == "270":
            ut, vt = 1 - sv, 1 - su
        else:  # false
            ut, vt = su, 1 - sv
        uv_list.append((u0 + (u1 - u0) * ut, 1 - v1 + (v1 - v0) * vt))
    return uv_list


def assign_uvs(mesh, uv_list):
    """按顶点索引把 uv 写入新建的 uv 层"""
    uv_layer = mesh.uv_layers.new()
    flat = [0.0] * (len(mesh.loops) * 2)
    for i, loop in enumerate(mesh.loops):
        u, v = uv_list[loop.vertex_index]
        flat[i * 2] = u
        flat[i * 2 + 1] = v
    uv_layer.data.foreach_set("uv", flat)


def _finish_atlas_region(name, data, atlas):
    """补全缺省字段并兼容 spine 4.x 的 bounds/offsets 写法"""
    if "bounds" in data:  # 4.x: bounds = x, y, w, h
        x, y, w, h = (v.strip() for v in data["bounds"].split(","))
        data["xy"] = f"{x}, {y}"
        data["size"] = f"{w}, {h}"
    if "offsets" in data:  # 4.x: offsets = ox, oy, ow, oh
        ox, oy, ow, oh = (v.strip() for v in data["offsets"].split(","))
        data["offset"] = f"{ox}, {oy}"
        data["orig"] = f"{ow}, {oh}"

    data.setdefault("offset", "0, 0")
    data.setdefault("orig", data.get("size", "0, 0"))
    rotate = data.get("rotate", "false")
    data["rotate"] = "true" if rotate == "90" else rotate
    data["index"] = int(data.get("index", -1))
    atlas[name] = data


def read_atlas(file_path):
    """解析 .atlas 图集文件

    按 "键: 值" 逐行解析而不是按行号定位, 字段缺失或顺序变化也能读;
    兼容 spine 3.x / 4.x 两种格式。多页图集只取第一页(与旧版行为一致)。
    """
    atlas = {}
    current = None
    current_name = None
    prev_blank = True

    with open(file_path, 'r', encoding='utf-8') as file:
        for raw in file:
            line = raw.strip()
            if not line:
                prev_blank = True
                continue

            if ":" in line:
                key, _, value = line.partition(":")
                key, value = key.strip(), value.strip()
                if current is None:
                    # 页头字段 (size / format / filter / repeat ...)
                    if key == "size":
                        w, h = value.split(",")
                        atlas["size"] = (int(w), int(h))
                    else:
                        atlas[key] = value
                else:
                    current[key] = value
                prev_blank = False
                continue

            # 不带冒号的行: 第一次出现是图片名, 之后是区域名
            if "image" not in atlas:
                atlas["image"] = line
            elif prev_blank:
                # 空行后又出现图片名 => 第二页图集, 暂不支持
                print(f"[spine2d] 多页图集暂不支持, 忽略后续图集页: {line}")
                break
            else:
                if current_name is not None:
                    _finish_atlas_region(current_name, current, atlas)
                current_name = line
                current = {}
            prev_blank = False

    if current_name is not None and current:
        _finish_atlas_region(current_name, current, atlas)
    return atlas


def create_bones(rig_name, bones_info, scale):
    armt = bpy.data.armatures.new(rig_name)
    armt.display_type = "STICK"

    new_rig = bpy.data.objects.new(rig_name, armt)
    bpy.context.scene.collection.objects.link(new_rig)
    bpy.context.view_layer.objects.active = new_rig
    new_rig.show_in_front = True
    new_rig.select_set(state=True)

    bpy.ops.object.mode_set(mode="EDIT")
    bone_dict = {}

    for bone in bones_info:
        parent_name = bone.get("parent")
        length = bone.get("length", 1) * scale
        transform = bone.get('transform')

        new_bone = armt.edit_bones.new(name=bone["name"])
        bone_dict[bone["name"]] = new_bone

        if parent_name:
            parent_bone = bone_dict[parent_name]
            new_bone.parent = parent_bone
            new_bone.head = parent_bone.head
            new_bone.use_connect = False
        else:
            new_bone.head = Vector((0, 0, 0))

        # 没写长度或长度为 0 时给一个极小尾巴, 避免零长骨骼被 Blender 自动删除
        if length <= 0 or length == scale:
            new_bone.tail = new_bone.head + Vector((scale * 0.01, 0, 0))
        else:
            new_bone.tail = new_bone.head + Vector((length, 0, 0))

        if transform in ("noRotationOrReflection", "onlyTranslation"):
            new_bone.use_inherit_rotation = False

    # 在姿态模式下摆好初始位置和旋转, 再应用为静置姿态
    bpy.ops.object.mode_set(mode='POSE')
    for bone in bones_info:
        pbone = new_rig.pose.bones[bone["name"]]
        pbone.location = 0, bone.get("x", 0) * scale, bone.get("y", 0) * scale
        pbone.rotation_mode = 'XYZ'
        pbone.rotation_euler[0] = math.radians(bone.get("rotation", 0))

    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    return new_rig


def get_or_create_vertex_group(obj, group_name):
    return obj.vertex_groups.get(group_name) or obj.vertex_groups.new(name=group_name)


def create_mesh(mesh_name, bone_name, point_data, bone_list, atlas, bone_matrix, scale):
    attach_type = point_data.get('type')
    if attach_type not in (None, 'region', 'mesh'):
        # clipping / boundingbox / path / point 等附件不产生网格
        print(f"[spine2d] 跳过不支持的附件类型 {attach_type}: {mesh_name}")
        return None

    # 附件可以指定 path/name 指向图集里的其它区域
    region_name = point_data.get('path') or point_data.get('name') or mesh_name

    if attach_type != 'mesh':
        # region 附件: 一个带旋转/缩放的矩形贴片
        width = point_data.get('width', 0) * scale * point_data.get('scaleX', 1)
        height = point_data.get('height', 0) * scale * point_data.get('scaleY', 1)
        mesh_rot = point_data.get('rotation', 0)
        x = point_data.get('x', 0) * scale
        y = point_data.get('y', 0) * scale
        _bone = bone_matrix.get(bone_name)

        euler = _bone['matrix_eular'][0]
        region_x = x * math.cos(euler) - y * math.sin(euler)
        region_y = x * math.sin(euler) + y * math.cos(euler)
        rotate = euler + math.radians(mesh_rot)
        cr, sr = math.cos(rotate), math.sin(rotate)
        sx, sz = _bone['matrix_scale'][1], _bone['matrix_scale'][2]
        tx, tz = _bone['matrix_translation'][0], _bone['matrix_translation'][2]

        corners = [(-width / 2, height / 2), (width / 2, height / 2),
                   (-width / 2, -height / 2), (width / 2, -height / 2)]
        mesh_vertices = [
            ((cx * cr - cy * sr + region_x) * sx + tx,
             0,
             (cx * sr + cy * cr + region_y) * sz + tz)
            for cx, cy in corners
        ]
        edge_list = []
        face_list = [(0, 1, 3, 2)]
        uvs = [0, 0, 1, 0, 0, 1, 1, 1]
        weight_data = None  # 全部顶点绑到插槽骨骼
    else:
        # mesh 附件: 自由网格, 可能带骨骼权重
        vertices = point_data.get('vertices')
        edges = point_data.get('edges') or []
        triangles = point_data.get('triangles')
        uvs = point_data.get('uvs')

        edge_list = [(int(edges[i] / 2), int(edges[i + 1] / 2))
                     for i in range(0, len(edges), 2)]
        face_list = [tuple(triangles[i:i + 3]) for i in range(0, len(triangles), 3)]

        mesh_vertices = []
        # 无权重时 vertices 只是 (x, y) 平铺, 长度和 uvs 一致; 否则是加权格式
        if len(vertices) == len(uvs):
            weight_data = None
            _bone = bone_matrix.get(bone_name)
            euler = _bone['matrix_eular'][0]
            c, s = math.cos(euler), math.sin(euler)
            sc = _bone['matrix_scale'][1]
            tx, tz = _bone['matrix_translation'][0], _bone['matrix_translation'][2]
            for i in range(0, len(vertices), 2):
                x = vertices[i] * scale
                y = vertices[i + 1] * scale
                mesh_vertices.append(((x * c - y * s) * sc + tx,
                                      0,
                                      (y * c + x * s) * sc + tz))
        else:
            weight_data = get_vertices_list(vertices, scale=scale)
            for influences in weight_data:
                x = y = 0.0
                for inf in influences:
                    _bone = bone_matrix.get(bone_list[inf['bone_idx']]["name"])
                    euler = _bone['matrix_eular'][0]
                    c, s = math.cos(euler), math.sin(euler)
                    sc = _bone['matrix_scale'][1]
                    x += ((inf['x'] * c - inf['y'] * s) * sc
                          + _bone['matrix_translation'][0]) * inf['weight']
                    y += ((inf['y'] * c + inf['x'] * s) * sc
                          + _bone['matrix_translation'][2]) * inf['weight']
                mesh_vertices.append((x, 0, y))

    mesh = bpy.data.meshes.new(mesh_name)
    mesh_obj = bpy.data.objects.new(mesh_name, mesh)
    mesh.from_pydata(mesh_vertices, edge_list, face_list)
    mesh.update()
    bpy.context.scene.collection.objects.link(mesh_obj)

    uv_list = create_uv(region_name, uvs, atlas)
    if uv_list is not None and len(uv_list) == len(mesh_vertices):
        assign_uvs(mesh, uv_list)

    if weight_data is None:
        vertex_group = get_or_create_vertex_group(mesh_obj, bone_name)
        vertex_group.add(list(range(len(mesh_vertices))), 1.0, 'REPLACE')
    else:
        group_cache = {}
        for idx, influences in enumerate(weight_data):
            for inf in influences:
                b_name = bone_list[inf['bone_idx']]["name"]
                vgroup = group_cache.get(b_name)
                if vgroup is None:
                    vgroup = get_or_create_vertex_group(mesh_obj, b_name)
                    group_cache[b_name] = vgroup
                vgroup.add([idx], inf['weight'], 'REPLACE')

    return mesh_obj


def _get_pixels(image):
    """用 foreach_get 批量读像素, 比 image.pixels[:] 快得多"""
    w, h = image.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(buf)
    return buf.reshape((h, w, 4))


def extend_image(image, new_width, new_height):
    """把图片扩展到指定尺寸, 空白处填透明"""
    old_width, old_height = image.size
    new_image = bpy.data.images.new(image.name + "_extended",
                                    width=new_width, height=new_height, alpha=True)
    new_pixels = np.zeros((new_height, new_width, 4), dtype=np.float32)
    new_pixels[:old_height, :old_width, :] = _get_pixels(image)
    new_image.pixels.foreach_set(new_pixels.ravel())
    return new_image


def create_new_image(image1, image2):
    """把两张图上下拼接, 宽度不同时先补齐"""
    width1, height1 = image1.size
    width2, height2 = image2.size
    max_width = max(width1, width2)

    if width1 < max_width:
        image1 = extend_image(image1, max_width, height1)
    if width2 < max_width:
        image2 = extend_image(image2, max_width, height2)

    combined_height = height1 + height2
    combined_image = bpy.data.images.new("CombinedImage", width=max_width,
                                         height=combined_height, alpha=True)

    combined_pixels = np.zeros((combined_height, max_width, 4), dtype=np.float32)
    combined_pixels[:height1, :, :] = _get_pixels(image1)
    combined_pixels[height1:, :, :] = _get_pixels(image2)
    combined_image.pixels.foreach_set(combined_pixels.ravel())

    return combined_image


def change_texture_path(obj, new_image_path):
    if obj.type != 'MESH':
        return
    for mat in obj.data.materials:
        if mat and mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    node.image.filepath = new_image_path


def get_skin_attachments(json_data):
    """取默认皮肤的附件表, 兼容 3.8+ 的列表格式和更早的字典格式"""
    skins = json_data.get("skins")
    if isinstance(skins, dict):
        return skins.get("default") or next(iter(skins.values()))
    return skins[0].get("attachments")


def create_mesh_all(json_data, atlas, rig, image_path, bone_matrix, scale, add):
    final_image = image_path
    max_meshindex = 0
    image1 = None
    image2 = None

    if add:
        # 找到已有网格的最大序号和旧贴图路径, 把新旧贴图拼成一张
        oldimg_path = ""
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            meshindex = obj.data.get("meshindex")
            if meshindex and meshindex > max_meshindex:
                max_meshindex = meshindex
                for mat in obj.data.materials:
                    if mat and mat.use_nodes:
                        for node in mat.node_tree.nodes:
                            if node.type == 'TEX_IMAGE' and node.image:
                                oldimg_path = node.image.filepath

        if oldimg_path != "":
            final_image = os.path.splitext(image_path)[0] + "_all.png"

            image1 = bpy.data.images.load(oldimg_path)
            image2 = bpy.data.images.load(image_path)
            combined_image = create_new_image(image1, image2)
            combined_image.filepath_raw = final_image
            combined_image.file_format = 'PNG'
            combined_image.save()

            width1, height1 = image1.size
            width2, height2 = image2.size
            # 旧网格 uv 压缩到拼接图的下半部分
            old_h_scale = height1 / (height1 + height2)
            old_w_scale = width1 / width2 if width1 < width2 else 1.0
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.data.get("meshindex"):
                    change_texture_path(obj, final_image)
                    uv_layer = obj.data.uv_layers.active
                    if uv_layer is None:
                        continue
                    for uv_data in uv_layer.data:
                        uv_data.uv.x *= old_w_scale
                        uv_data.uv.y *= old_h_scale

    slots = json_data.get("slots")
    bone_list = json_data.get("bones")
    bone_info = {}
    attachment_list = {}
    bone_z = {}
    mesh_index = {}

    # 序号从已有最大值往后排, 避免和旧网格重叠; z 按插槽顺序错开做前后排序
    mesh_index_add = max_meshindex + 1
    z_add = -0.05 * mesh_index_add
    for slot in slots:
        slot_name = slot.get('name')
        z_add -= 0.05
        bone_info[slot_name] = slot.get('bone')
        bone_z[slot_name] = z_add
        mesh_index[slot_name] = mesh_index_add
        mesh_index_add += 1

        if slot.get('attachment'):
            attachment_list[slot_name] = slot.get('attachment')

    # 新网格 uv 需要整体映射到拼接图的上半部分
    new_uv_transform = None
    if add and image1 is not None:
        width1, height1 = image1.size
        width2, height2 = image2.size
        new_uv_transform = (
            width2 / width1 if width2 < width1 else 1.0,  # x 缩放
            height2 / (height1 + height2),                # y 缩放
            height1 / (height1 + height2),                # y 偏移
        )

    mesh_data = get_skin_attachments(json_data)
    material = create_materials('PDXmat_All', final_image)

    for key, value in mesh_data.items():
        bone_name = bone_info.get(key)
        attachment = attachment_list.get(key)
        for mesh_name, point_data in value.items():
            obj = create_mesh(mesh_name, bone_name, point_data, bone_list,
                              atlas, bone_matrix, scale)
            if obj is None:
                continue

            # 只显示插槽当前激活的附件
            if attachment != mesh_name:
                obj.hide_viewport = True
                obj.hide_render = True

            obj.location.y += bone_z[key]
            obj.data["meshindex"] = mesh_index[key]

            modifier = obj.modifiers.new(name="Armature", type='ARMATURE')
            modifier.object = rig
            modifier.use_vertex_groups = True

            if new_uv_transform is not None:
                w_scale, h_scale, h_offset = new_uv_transform
                uv_layer = obj.data.uv_layers.active
                if uv_layer is not None:
                    for uv_data in uv_layer.data:
                        uv_data.uv.x *= w_scale
                        uv_data.uv.y = uv_data.uv.y * h_scale + h_offset

            if obj.data.materials:
                obj.data.materials[0] = material
            else:
                obj.data.materials.append(material)


def create_animations(animations_data, rig, scale):
    """直接写 F 曲线生成动画, 不经过 bpy.ops, 速度快且不依赖选择状态

    坐标换算约定(与骨骼创建逻辑一致):
    - spine 的旋转角 == pose 骨骼 rotation_euler[0]
    - spine 的位移在父骨骼空间中, 用静置矩阵换算到骨骼本地空间
    """
    if not animations_data:
        return

    animation = animations_data.get("normal")
    if not animation:
        animation = next((v for v in animations_data.values() if "bones" in v), None)
    if not animation:
        return

    bone_anim = animation.get("bones", {})
    frame_end = 0
    for e in animation.get("events") or []:
        if e.get("name") == "finish":
            frame_end = int(e.get("time", 0) * FPS)

    anim_data = rig.animation_data_create()
    action = bpy.data.actions.new(name=f"{rig.name}_action")
    anim_data.action = action

    for bone_name, timelines in bone_anim.items():
        pbone = rig.pose.bones.get(bone_name)
        if pbone is None:
            print(f"[spine2d] 动画引用了不存在的骨骼: {bone_name}")
            continue
        base_path = f'pose.bones["{bone_name}"].'

        rotate_keys = timelines.get("rotate")
        if rotate_keys:
            fcurve = action.fcurves.new(base_path + "rotation_euler",
                                        index=0, action_group=bone_name)
            fcurve.keyframe_points.add(len(rotate_keys))
            prev_angle = None
            for kp, key in zip(fcurve.keyframe_points, rotate_keys):
                frame = int(key.get("time", 0) * FPS)
                frame_end = max(frame_end, frame)
                angle = math.radians(key.get("angle", 0))
                # 展开角度使相邻关键帧走最短路径, 和 spine 的插值一致
                if prev_angle is not None:
                    while angle - prev_angle > math.pi:
                        angle -= 2 * math.pi
                    while angle - prev_angle < -math.pi:
                        angle += 2 * math.pi
                prev_angle = angle
                kp.co = (frame, angle)
                kp.interpolation = 'CONSTANT' if key.get("curve") == "stepped" else 'LINEAR'
            fcurve.update()

        translate_keys = timelines.get("translate")
        if translate_keys:
            fcurves = [action.fcurves.new(base_path + "location",
                                          index=i, action_group=bone_name)
                       for i in range(3)]
            for fc in fcurves:
                fc.keyframe_points.add(len(translate_keys))

            # spine 位移在父骨骼空间: 先转到骨架空间, 再转到自身静置空间
            rest_inv = pbone.bone.matrix_local.to_3x3().inverted()
            parent_rot = (pbone.parent.bone.matrix_local.to_3x3()
                          if pbone.parent else None)

            for i, key in enumerate(translate_keys):
                frame = int(key.get("time", 0) * FPS)
                frame_end = max(frame_end, frame)
                dx = key.get("x", 0) * scale
                dy = key.get("y", 0) * scale
                if parent_rot is not None:
                    loc = rest_inv @ (parent_rot @ Vector((0.0, dx, dy)))
                else:
                    loc = rest_inv @ Vector((dx, 0.0, dy))
                interp = 'CONSTANT' if key.get("curve") == "stepped" else 'LINEAR'
                for axis in range(3):
                    kp = fcurves[axis].keyframe_points[i]
                    kp.co = (frame, loc[axis])
                    kp.interpolation = interp
            for fc in fcurves:
                fc.update()

    bpy.context.scene.frame_end = max(frame_end, 1)


def bind_ik(rig, ik_info):
    for ik_data in ik_info:
        # IK 约束加在链末端骨骼上
        end_bone = rig.pose.bones.get(ik_data["bones"][-1])
        if end_bone is None:
            print(f"[spine2d] IK 引用了不存在的骨骼: {ik_data['bones'][-1]}")
            continue

        constraint = end_bone.constraints.new(type='IK')
        constraint.name = f"IK_{ik_data['name']}"
        constraint.target = rig
        constraint.subtarget = ik_data["target"]
        constraint.chain_count = len(ik_data["bones"])

        if ik_data.get("bendPositive"):
            # 根据 bendPositive 控制弯曲方向
            constraint.pole_angle = 0 if ik_data["bendPositive"] != "false" else math.pi


def reload_uvs(json_data, atlas, image_path):
    """重载模式: 只按图集重建已有网格的 uv 并刷新贴图路径"""
    mesh_data = get_skin_attachments(json_data)
    mesh_uv = {}
    for value in mesh_data.values():
        for mesh_name, point_data in value.items():
            if point_data.get('type') == 'mesh':
                uvs = point_data.get('uvs')
            else:
                uvs = [0, 0, 1, 0, 0, 1, 1, 1]
            region_name = point_data.get('path') or point_data.get('name') or mesh_name
            uv_list = create_uv(region_name, uvs, atlas)
            if uv_list is not None:
                mesh_uv[mesh_name] = uv_list

    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        uv_list = mesh_uv.get(obj.name)
        if uv_list and len(uv_list) == len(mesh.vertices):
            if mesh.uv_layers.active:
                mesh.uv_layers.remove(mesh.uv_layers.active)
            assign_uvs(mesh, uv_list)
        change_texture_path(obj, image_path)


def import_jsonfile(json_path, add=False, reload=False):
    scale = 0.01

    folder_path = os.path.dirname(json_path)
    base_name = os.path.splitext(os.path.basename(json_path))[0]
    atlas_path = os.path.join(folder_path, base_name + ".atlas")
    if not os.path.exists(atlas_path):
        raise FileNotFoundError(f"找不到同名图集文件: {atlas_path}")

    atlas = read_atlas(atlas_path)
    image_path = os.path.join(folder_path, atlas.get("image", ""))

    with open(json_path, 'r', encoding='utf-8') as file:
        content = file.read()
    json_data = json.loads(convert_to_latin1_compatible(content))

    if reload:
        reload_uvs(json_data, atlas, image_path)
        return

    # 创建骨骼
    bones_info = json_data.get("bones")
    rig_name = base_name + "_rig"
    new_rig = create_bones(rig_name, bones_info, scale)

    ik_info = json_data.get("ik")
    if ik_info:
        bind_ik(new_rig, ik_info)

    bone_matrix = _get_bone_matrix_dict(new_rig)

    # 创建网格
    create_mesh_all(json_data, atlas, new_rig, image_path, bone_matrix, scale, add)

    # 创建动画(追加模式沿用场景里已有的动画)
    if not add:
        create_animations(json_data.get("animations"), new_rig, scale)
