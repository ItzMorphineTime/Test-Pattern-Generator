"""Simple, seamless scrolling colour-loop exporter for Blender 5.1+."""

from __future__ import annotations

import os

import bpy
from bpy.props import FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup


bl_info = {
    "name": "Simple Projection Colour Loop",
    "author": "Will Harkin",
    "version": (1, 1, 0),
    "blender": (5, 1, 0),
    "location": "3D View > Sidebar > Colour Loop",
    "description": "Export a seamless, gently scrolling colour video",
    "category": "Render",
}


SCENE_NAME = "Projection Colour Loop"
COLLECTION_NAME = "Colour Loop | Generated"
MATERIAL_NAME = "Colour Loop | Material"
KNOWN_VIDEO_EXTENSIONS = {
    ".avi",
    ".dv",
    ".flv",
    ".m2v",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogv",
    ".webm",
}


def frame_count(duration: float, frame_rate: float) -> int:
    """Return the nearest whole frame count, with a minimum of one frame."""
    return max(1, int(round(float(duration) * float(frame_rate))))


def preferred_containers(codec: str) -> tuple[str, ...]:
    """Return sensible container preferences for a Blender FFmpeg codec."""
    codec = str(codec).upper()
    mapping = {
        "AV1": ("MKV", "WEBM", "MPEG4"),
        "DNXHD": ("QUICKTIME", "MKV"),
        "DV": ("DV", "AVI", "QUICKTIME"),
        "FFV1": ("MKV", "AVI"),
        "FLASH": ("FLASH", "AVI"),
        "H264": ("MPEG4", "MKV", "QUICKTIME"),
        "H265": ("MPEG4", "MKV", "QUICKTIME"),
        "HUFFYUV": ("AVI", "MKV"),
        "MPEG1": ("MPEG1", "MPEG2"),
        "MPEG2": ("MPEG2", "MPEG1"),
        "MPEG4": ("MPEG4", "MKV"),
        "PNG": ("QUICKTIME", "MKV"),
        "PRORES": ("QUICKTIME", "MKV"),
        "QTRLE": ("QUICKTIME",),
        "THEORA": ("OGG", "MKV"),
        "VP9": ("WEBM", "MKV"),
        "WEBM": ("WEBM", "MKV"),
    }
    return mapping.get(codec, ("MPEG4", "MKV", "QUICKTIME", "AVI"))


def _rna_property(owner, property_name):
    try:
        return owner.bl_rna.properties.get(property_name)
    except (AttributeError, TypeError):
        return None


def _enum_identifiers(owner, property_name: str) -> set[str]:
    prop = _rna_property(owner, property_name)
    if prop is None or getattr(prop, "type", None) != "ENUM":
        return set()
    try:
        return {item.identifier for item in prop.enum_items}
    except (AttributeError, TypeError, RuntimeError):
        return set()


def _set_enum_if_available(owner, property_name: str, value: str) -> bool:
    if value not in _enum_identifiers(owner, property_name):
        return False
    try:
        setattr(owner, property_name, value)
        return True
    except (AttributeError, TypeError, ValueError):
        return False


def _enable_ffmpeg_output(render) -> bool:
    """Enable video output using Blender 5's media type, with a legacy fallback."""
    build_options = getattr(bpy.app, "build_options", None)
    if build_options is not None and getattr(build_options, "ffmpeg", True) is False:
        return False

    image_settings = getattr(render, "image_settings", None)
    if image_settings is not None and _set_enum_if_available(
        image_settings, "media_type", "VIDEO"
    ):
        return True

    # Before Blender 5, movie output was selected from the file-format enum.
    owners = [render]
    if image_settings is not None:
        owners.append(image_settings)

    preferred_names = ("file_format", "output_format", "format")
    for owner in owners:
        for property_name in preferred_names:
            if _set_enum_if_available(owner, property_name, "FFMPEG"):
                return True

    # Final compatibility fallback: search only the two render-output structs.
    for owner in owners:
        try:
            properties = owner.bl_rna.properties
        except AttributeError:
            continue
        for prop in properties:
            property_name = getattr(prop, "identifier", "")
            if property_name and _set_enum_if_available(owner, property_name, "FFMPEG"):
                return True
    return False


def _choose_available_container(ffmpeg, codec: str) -> str | None:
    available = _enum_identifiers(ffmpeg, "format")
    for container in preferred_containers(codec):
        if container in available:
            return container
    return next(iter(sorted(available)), None)


def _strip_known_video_extension(path: str) -> str:
    root, extension = os.path.splitext(path)
    return root if extension.lower() in KNOWN_VIDEO_EXTENSIONS else path


def _set_engine(scene) -> None:
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if _set_enum_if_available(scene.render, "engine", engine):
            return


def _remove_generated_collection(scene) -> None:
    collection = scene.collection.children.get(COLLECTION_NAME)
    if collection is None:
        return
    for obj in list(collection.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is None or data.users:
            continue
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
    scene.collection.children.unlink(collection)
    bpy.data.collections.remove(collection)


def _make_plane_mesh(name: str, aspect: float):
    width = 2.0 * aspect
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [
            (-width / 2.0, -1.0, 0.0),
            (width / 2.0, -1.0, 0.0),
            (width / 2.0, 1.0, 0.0),
            (-width / 2.0, 1.0, 0.0),
        ],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    uv_by_vertex = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = uv_by_vertex[loop.vertex_index]
    return mesh


def _make_colour_material(total_frames: int):
    old_material = bpy.data.materials.get(MATERIAL_NAME)
    if old_material is not None:
        bpy.data.materials.remove(old_material, do_unlink=True)

    material = bpy.data.materials.new(MATERIAL_NAME)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (520.0, 0.0)
    emission = nodes.new("ShaderNodeEmission")
    emission.location = (280.0, 0.0)
    emission.inputs[1].default_value = 1.0
    combine = nodes.new("ShaderNodeCombineColor")
    combine.location = (40.0, 0.0)
    combine.mode = "HSV"
    combine.inputs[1].default_value = 0.88
    combine.inputs[2].default_value = 0.9
    fraction = nodes.new("ShaderNodeMath")
    fraction.operation = "FRACT"
    fraction.location = (-180.0, 0.0)
    add = nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    add.location = (-400.0, 0.0)
    time_value = nodes.new("ShaderNodeValue")
    time_value.label = "Seamless loop time"
    time_value.location = (-620.0, -120.0)
    driver = time_value.outputs[0].driver_add("default_value").driver
    driver.expression = f"(frame - 1.0) / {float(total_frames):.1f}"
    separate = nodes.new("ShaderNodeSeparateXYZ")
    separate.location = (-620.0, 80.0)
    texture = nodes.new("ShaderNodeTexCoord")
    texture.location = (-840.0, 80.0)

    links.new(texture.outputs["UV"], separate.inputs[0])
    links.new(separate.outputs["X"], add.inputs[0])
    links.new(time_value.outputs[0], add.inputs[1])
    links.new(add.outputs[0], fraction.inputs[0])
    links.new(fraction.outputs[0], combine.inputs[0])
    links.new(combine.outputs[0], emission.inputs[0])
    links.new(emission.outputs[0], output.inputs["Surface"])
    return material


def _build_colour_scene(scene, width: int, height: int, total_frames: int) -> None:
    _remove_generated_collection(scene)
    collection = bpy.data.collections.new(COLLECTION_NAME)
    scene.collection.children.link(collection)

    aspect = width / height
    mesh = _make_plane_mesh("Colour Loop | Screen", aspect)
    plane = bpy.data.objects.new("Colour Loop | Screen", mesh)
    collection.objects.link(plane)
    plane.data.materials.append(_make_colour_material(total_frames))

    camera_data = bpy.data.cameras.new("Colour Loop | Camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 2.0
    camera = bpy.data.objects.new("Colour Loop | Camera", camera_data)
    camera.location = (0.0, 0.0, 10.0)
    collection.objects.link(camera)
    scene.camera = camera

    world = scene.world or bpy.data.worlds.new("Colour Loop | World")
    scene.world = world
    world.color = (0.0, 0.0, 0.0)
    _set_engine(scene)


def _copy_settings(source, target) -> None:
    for name in ("width", "height", "frame_rate", "duration", "output_path"):
        setattr(target, name, getattr(source, name))


def _configure_output(scene, settings, codec: str) -> int:
    render = scene.render
    if not _enable_ffmpeg_output(render):
        version = getattr(bpy.app, "version_string", "this version")
        raise RuntimeError(
            f"FFmpeg movie output is not available in Blender {version}. "
            "Install an official Blender build with FFmpeg support."
        )

    total_frames = frame_count(settings.duration, settings.frame_rate)
    render.resolution_x = settings.width
    render.resolution_y = settings.height
    render.resolution_percentage = 100
    integer_fps = max(1, int(round(settings.frame_rate)))
    render.fps = integer_fps
    render.fps_base = integer_fps / settings.frame_rate
    render.film_transparent = False
    render.use_file_extension = True
    render.filepath = _strip_known_video_extension(settings.output_path)

    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.frame_set(1)

    ffmpeg = render.ffmpeg
    container = _choose_available_container(ffmpeg, codec)
    if container is None or not _set_enum_if_available(ffmpeg, "format", container):
        raise RuntimeError("Blender did not expose a usable FFmpeg video container.")
    if not _set_enum_if_available(ffmpeg, "codec", codec):
        raise RuntimeError(f"The {codec} codec is not available with this Blender build.")

    _set_enum_if_available(ffmpeg, "audio_codec", "NONE")
    if codec in {"H264", "H265", "MPEG4", "AV1", "VP9"}:
        _set_enum_if_available(ffmpeg, "constant_rate_factor", "HIGH")
        _set_enum_if_available(ffmpeg, "ffmpeg_preset", "GOOD")
    elif codec in {"FFV1", "HUFFYUV", "PNG", "QTRLE"}:
        _set_enum_if_available(ffmpeg, "constant_rate_factor", "LOSSLESS")

    image_settings = render.image_settings
    _set_enum_if_available(image_settings, "color_mode", "RGB")
    _set_enum_if_available(image_settings, "color_depth", "8")

    try:
        _set_enum_if_available(scene.view_settings, "view_transform", "Standard")
        _set_enum_if_available(scene.view_settings, "look", "Medium High Contrast")
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except (AttributeError, TypeError, ValueError):
        pass

    absolute_path = bpy.path.abspath(render.filepath)
    output_directory = os.path.dirname(absolute_path)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)
    return total_frames


class PCL_Settings(PropertyGroup):
    width: IntProperty(
        name="Width",
        description="Output width in pixels",
        default=1920,
        min=16,
        max=65536,
    )
    height: IntProperty(
        name="Height",
        description="Output height in pixels",
        default=1080,
        min=16,
        max=65536,
    )
    frame_rate: FloatProperty(
        name="Frame Rate",
        description="Frames per second",
        default=25.0,
        min=1.0,
        max=240.0,
        precision=3,
    )
    duration: FloatProperty(
        name="Duration",
        description="Video duration in seconds; the loop always completes exactly once",
        default=10.0,
        min=0.1,
        max=3600.0,
        precision=2,
        subtype="TIME",
    )
    output_path: StringProperty(
        name="Output",
        description="Video output path; Blender adds the correct extension",
        default="//colour_loop",
        subtype="FILE_PATH",
    )


class PCL_OT_ExportLoop(Operator):
    bl_idname = "pcl.export_loop"
    bl_label = "Export Colour Loop"
    bl_description = "Build and render the seamless scrolling colour video"
    bl_options = {"REGISTER"}

    def execute(self, context):
        source_scene = context.scene
        settings = source_scene.pcl_settings
        codec = source_scene.render.ffmpeg.codec

        if codec in {"H264", "H265", "MPEG4"} and (
            settings.width % 2 or settings.height % 2
        ):
            self.report(
                {"ERROR"},
                "This codec requires even width and height values.",
            )
            return {"CANCELLED"}

        try:
            scene = bpy.data.scenes.get(SCENE_NAME)
            if scene is None:
                scene = bpy.data.scenes.new(SCENE_NAME)
            _copy_settings(settings, scene.pcl_settings)
            total_frames = _configure_output(scene, scene.pcl_settings, codec)
            _build_colour_scene(
                scene,
                scene.pcl_settings.width,
                scene.pcl_settings.height,
                total_frames,
            )
            if context.window is not None:
                context.window.scene = scene
            bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Rendering {total_frames} frames as {codec}",
        )
        return {"FINISHED"}


class PCL_PT_ColourLoop(Panel):
    bl_label = "Colour Loop"
    bl_idname = "PCL_PT_colour_loop"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Colour Loop"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.pcl_settings

        resolution = layout.box()
        resolution.label(text="Video")
        row = resolution.row(align=True)
        row.prop(settings, "width")
        row.prop(settings, "height")
        resolution.prop(settings, "frame_rate")
        resolution.prop(settings, "duration")
        resolution.prop(context.scene.render.ffmpeg, "codec")
        resolution.prop(settings, "output_path")

        frames = frame_count(settings.duration, settings.frame_rate)
        layout.label(text=f"{frames:,} frames • one seamless colour cycle")
        button = layout.row()
        button.scale_y = 1.7
        button.operator("pcl.export_loop", icon="RENDER_ANIMATION")


CLASSES = (
    PCL_Settings,
    PCL_OT_ExportLoop,
    PCL_PT_ColourLoop,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pcl_settings = PointerProperty(type=PCL_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "pcl_settings"):
        del bpy.types.Scene.pcl_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
