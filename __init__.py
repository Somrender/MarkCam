bl_info = {
    "name": "MarkCam",
    "author": "Som Render",
    "version": (1, 0, 7),
    "blender": (4, 5, 0),
    "location": "Dope Sheet (Timeline) Header",
    "description": "Create camera from view (Shift/Ctrl), bind camera to current-frame marker, remove markers (Ctrl+X removes ALL with confirm).",
    "category": "Animation",
}

import bpy
from bpy.props import BoolProperty


# ---------- Utilities ----------

def is_timeline_area(context):
    area = context.area
    return (
        area is not None
        and area.type == 'DOPESHEET_EDITOR'
        and getattr(area, "ui_type", "") == 'TIMELINE'
    )

def get_marker_at_frame(scene, frame):
    for m in scene.timeline_markers:
        if m.frame == frame:
            return m
    return None

def get_all_markers_at_frame(scene, frame):
    return [m for m in scene.timeline_markers if m.frame == frame]

def get_view3d_refs(context):
    win = context.window
    scr = win.screen if win else None
    if not scr:
        return None, None, None
    for area in scr.areas:
        if area.type == 'VIEW_3D':
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            space = area.spaces.active
            if region and space:
                return area, space, region
    return None, None, None


# ---------- Operators ----------

class QCM_OT_camera_button(bpy.types.Operator):
    bl_idname = "qcm.camera_button"
    bl_label = "Camera / Marker"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        ctrl = bool(event and event.ctrl)
        shift = bool(event and event.shift)
        if ctrl:
            return self._add_camera_from_view_and_bind_marker(context)
        elif shift:
            return self._add_camera_from_view_only(context)
        else:
            return self._bind_active_camera_to_marker(context)

    # Core creating (align camera to current 3D view)
    def _create_and_align_camera_to_view(self, context):
        area, space, region = get_view3d_refs(context)
        if not area:
            self.report({'WARNING'}, "No visible 3D View to align camera to")
            return None

        r3d = space.region_3d
        cam_data = bpy.data.cameras.new("Camera")
        cam_obj = bpy.data.objects.new(cam_data.name, cam_data)

        target_coll = context.view_layer.active_layer_collection.collection
        target_coll.objects.link(cam_obj)

        for obj in context.view_layer.objects:
            obj.select_set(False)
        cam_obj.select_set(True)
        context.view_layer.objects.active = cam_obj

        cam_obj.matrix_world = r3d.view_matrix.inverted()
        if hasattr(space, "lens"):
            cam_obj.data.lens = space.lens

        context.scene.camera = cam_obj
        r3d.view_perspective = 'CAMERA'
        return cam_obj

    def _add_camera_from_view_only(self, context):
        cam = self._create_and_align_camera_to_view(context)
        return {'FINISHED'} if cam else {'CANCELLED'}

    def _add_camera_from_view_and_bind_marker(self, context):
        cam = self._create_and_align_camera_to_view(context)
        if not cam:
            return {'CANCELLED'}
        scene = context.scene
        frame = scene.frame_current
        marker = get_marker_at_frame(scene, frame) or scene.timeline_markers.new(name=cam.name, frame=frame)
        marker.camera = cam
        return {'FINISHED'}

    def _bind_active_camera_to_marker(self, context):
        cam = context.view_layer.objects.active
        if cam is None or cam.type != 'CAMERA':
            self.report({'WARNING'}, "Active object must be a Camera (use Ctrl+Click to create one).")
            return {'CANCELLED'}
        scene = context.scene
        frame = scene.frame_current
        marker = get_marker_at_frame(scene, frame) or scene.timeline_markers.new(name=cam.name, frame=frame)
        marker.camera = cam
        return {'FINISHED'}


class QCM_OT_remove_marker_at_current_frame(bpy.types.Operator):
    bl_idname = "qcm.remove_marker_at_current_frame"
    bl_label = "Remove ALL Markers"
    bl_options = {'REGISTER', 'UNDO'}

    delete_all: BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return len(context.scene.timeline_markers) > 0

    def invoke(self, context, event):
        if event and event.ctrl:
            self.delete_all = True
            return context.window_manager.invoke_confirm(self, event)
        self.delete_all = False
        return self.execute(context)

    def draw(self, context):
        self.layout.label(text="Delete ALL timeline markers?")

    def execute(self, context):
        scene = context.scene
        if self.delete_all:
            if not scene.timeline_markers:
                self.report({'INFO'}, "No markers to remove")
                return {'CANCELLED'}
            for m in list(scene.timeline_markers):
                scene.timeline_markers.remove(m)
            return {'FINISHED'}

        frame = scene.frame_current
        to_remove = get_all_markers_at_frame(scene, frame)
        if not to_remove:
            self.report({'WARNING'}, "select a marker or press ctrl+click")
            return {'CANCELLED'}
        for m in list(to_remove):
            scene.timeline_markers.remove(m)
        return {'FINISHED'}


# ---------- Header UI (next to Marker menu) ----------

def _draw_buttons_in_editor_menus(self, context):
    if not is_timeline_area(context):
        return
    layout = self.layout
    layout.separator(factor=0.4)  # small fixed padding
    row = layout.row(align=True)
    row.operator("qcm.camera_button", text="", icon='CAMERA_DATA')
    row.operator("qcm.remove_marker_at_current_frame", text="", icon='X')


# ---------- Registration ----------

_menu_targets = []

def _try_hook_editor_menus():
    targets = []
    if hasattr(bpy.types, "DOPESHEET_MT_editor_menus"):
        bpy.types.DOPESHEET_MT_editor_menus.append(_draw_buttons_in_editor_menus)
        targets.append(bpy.types.DOPESHEET_MT_editor_menus)
    if hasattr(bpy.types, "TIME_MT_editor_menus"):
        bpy.types.TIME_MT_editor_menus.append(_draw_buttons_in_editor_menus)
        targets.append(bpy.types.TIME_MT_editor_menus)
    return targets

def _unhook_editor_menus():
    for cls in _menu_targets:
        try:
            cls.remove(_draw_buttons_in_editor_menus)
        except Exception:
            pass

classes = (
    QCM_OT_camera_button,
    QCM_OT_remove_marker_at_current_frame,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    global _menu_targets
    _menu_targets = _try_hook_editor_menus()

def unregister():
    _unhook_editor_menus()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
