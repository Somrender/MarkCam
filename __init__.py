bl_info = {
    "name": "MarkCam",
    "author": "Som Render",
    "version": (2, 0, 1),
    "blender": (4, 5, 0),
    "location": "Dope Sheet (Timeline) Header + N-Panel",
    "description": "Camera from view (Shift/Ctrl), bind to markers, remove markers + Timeline N-panel ranges (supports multiple occurrences per camera).",
    "category": "Animation",
}

import bpy
from bpy.types import PropertyGroup, UIList, Panel, Operator
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

# ---------- Utilities ----------

def is_timeline_area(context):
    a = context.area
    return a and a.type == 'DOPESHEET_EDITOR' and getattr(a, "ui_type", "") == 'TIMELINE'

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

def camera_markers(scene):
    """All camera-bound timeline markers, sorted by frame."""
    items = [m for m in scene.timeline_markers if m.camera]
    items.sort(key=lambda m: m.frame)
    return items

def remove_all_markers(scene):
    for m in list(scene.timeline_markers):
        scene.timeline_markers.remove(m)

def make_frames_strictly_increasing(markers):
    """Ensure markers list has strictly increasing frames."""
    if not markers:
        return
    markers.sort(key=lambda m: m.frame)
    for i in range(1, len(markers)):
        if markers[i].frame <= markers[i - 1].frame:
            markers[i].frame = markers[i - 1].frame + 1

# ---------- Header Operators ----------

class QCM_OT_camera_button(Operator):
    bl_idname = "qcm.camera_button"
    bl_label = "Camera / Marker"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        ctrl = bool(event and event.ctrl)
        shift = bool(event and event.shift)
        if ctrl:
            result = self._add_camera_from_view_and_bind_marker(context)
        elif shift:
            result = self._add_camera_from_view_only(context)
        else:
            result = self._bind_active_camera_to_marker(context)
        sync_entries_from_scene(context.scene, cleanup=False)
        return result

    def _create_and_align_camera_to_view(self, context):
        area, space, region = get_view3d_refs(context)
        if not area:
            self.report({'WARNING'}, "No visible 3D View to align camera to")
            return None
        r3d = space.region_3d
        cam_data = bpy.data.cameras.new("Camera")
        cam_obj = bpy.data.objects.new(cam_data.name, cam_data)
        context.view_layer.active_layer_collection.collection.objects.link(cam_obj)
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

    # SHIFT + Click: add camera ONLY (no marker)
    def _add_camera_from_view_only(self, context):
        cam = self._create_and_align_camera_to_view(context)
        return {'FINISHED'} if cam else {'CANCELLED'}

    # CTRL + Click: add camera + bind marker at CURRENT frame
    def _add_camera_from_view_and_bind_marker(self, context):
        cam = self._create_and_align_camera_to_view(context)
        if not cam:
            return {'CANCELLED'}
        scn = context.scene
        f = scn.frame_current
        mk = get_marker_at_frame(scn, f) or scn.timeline_markers.new(name=cam.name, frame=f)
        mk.camera = cam
        return {'FINISHED'}

    # Click: bind active camera to marker at current frame
    def _bind_active_camera_to_marker(self, context):
        cam = context.view_layer.objects.active
        if not (cam and cam.type == 'CAMERA'):
            self.report({'WARNING'}, "Active object must be a Camera (use Ctrl+Click to create one).")
            return {'CANCELLED'}
        scn = context.scene
        f = scn.frame_current
        mk = get_marker_at_frame(scn, f) or scn.timeline_markers.new(name=cam.name, frame=f)
        mk.camera = cam
        return {'FINISHED'}

class QCM_OT_remove_marker_at_current_frame(Operator):
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
        scn = context.scene
        if self.delete_all:
            if not scn.timeline_markers:
                self.report({'INFO'}, "No markers to remove")
                return {'CANCELLED'}
            remove_all_markers(scn)
            sync_entries_from_scene(scn, cleanup=False)
            return {'FINISHED'}
        f = scn.frame_current
        to_remove = get_all_markers_at_frame(scn, f)
        if not to_remove:
            self.report({'WARNING'}, "No marker at current frame")
            return {'CANCELLED'}
        for m in list(to_remove):
            scn.timeline_markers.remove(m)
        sync_entries_from_scene(scn, cleanup=False)
        return {'FINISHED'}

# ---------- N-Panel Data (multiple occurrences) ----------

def _entry_changed(self, context):
    """Move ONLY the specific marker matched by (camera + orig_start)."""
    scn = context.scene
    if getattr(scn, "markcam_updating", False):
        return
    scn.markcam_updating = True
    try:
        cam = self.camera
        new = int(self.start)
        old = int(self.orig_start)

        # find the marker that used to be at 'old' for this camera
        mark = None
        for m in scn.timeline_markers:
            if m.camera == cam and m.frame == old:
                mark = m
                break
        # fallback: closest marker of this camera to old
        if mark is None:
            cand = [m for m in scn.timeline_markers if m.camera == cam]
            if cand:
                mark = min(cand, key=lambda m: abs(m.frame - old))

        if mark:
            mark.frame = new
            mark.name = cam.name
            self.orig_start = new
    finally:
        scn.markcam_updating = False

class MarkCamEntry(PropertyGroup):
    camera: PointerProperty(name="Camera", type=bpy.types.Object)
    start:  IntProperty(name="Start", default=1, update=_entry_changed)
    orig_start: IntProperty(name="Orig", default=1, options={'HIDDEN'})

class MARKCAM_OT_pick_and_jump(Operator):
    bl_idname = "markcam.pick_and_jump"
    bl_label = "Select & Jump"
    bl_description = "Select this camera and move the playhead to its start frame"
    bl_options = {'INTERNAL'}
    object_name: StringProperty()
    frame: IntProperty(default=1)

    def execute(self, context):
        scn = context.scene
        obj = scn.objects.get(self.object_name)
        if not obj:
            self.report({'WARNING'}, "Camera not found")
            return {'CANCELLED'}
        for o in context.view_layer.objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        scn.frame_set(int(self.frame))
        return {'FINISHED'}

def _build_entries_from_scene(scn):
    """One UI row per camera-bound marker occurrence."""
    scn.markcam_updating = True
    try:
        scn.markcam_entries.clear()
        for m in camera_markers(scn):
            e = scn.markcam_entries.add()
            e.camera = m.camera
            e.start = int(m.frame)
            e.orig_start = int(m.frame)
        scn.markcam_entries_index = 0 if scn.markcam_entries else -1
    finally:
        scn.markcam_updating = False

def sync_entries_from_scene(scn, cleanup=False):
    """Refresh list; optionally normalize frames to be strictly increasing."""
    if cleanup:
        marks = camera_markers(scn)
        make_frames_strictly_increasing(marks)
    _build_entries_from_scene(scn)

# ---------- N-Panel UI ----------

# Proportional columns (Camera | Start | End | Action)
NAME_F  = 0.45
START_F = 0.20
END_F   = 0.20
ACT_F   = 0.15

def _split_next(container, frac):
    return container.split(factor=frac, align=True)

def _four_columns(layout):
    s1 = _split_next(layout, NAME_F)
    c_name = s1.row(align=True)
    rest1 = _split_next(s1, START_F / (1.0 - NAME_F))
    c_start = rest1.row(align=True)
    rest2 = _split_next(rest1, END_F / (1.0 - NAME_F - START_F))
    c_end = rest2.row(align=True)
    c_act = rest2.row(align=True)
    return c_name, c_start, c_end, c_act

class MARKCAM_UL_entries(UIList):
    """One row per camera-bound marker occurrence."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        scn = context.scene
        cam = item.camera
        if not cam:
            layout.label(text="(missing)")
            return

        c_name, c_start, c_end, c_act = _four_columns(layout)

        # Camera name (inline rename)
        c_name.prop(cam, "name", text="", emboss=False)

        # Start
        ns = c_start.row(align=True); ns.scale_y = 0.9
        ns.prop(item, "start", text="")

        # End = next camera marker frame - 1 (or scene end)
        marks = camera_markers(scn)
        # find the entry corresponding to (camera, start) in sorted marks
        next_frame = scn.frame_end
        for m in marks:
            if m.frame > item.start:
                next_frame = m.frame - 1
                break
        if next_frame < item.start:
            next_frame = item.start
        ne = c_end.row(align=True); ne.scale_y = 0.9
        ne.label(text=str(next_frame))

        # Action: select camera + jump
        is_active = (context.view_layer.objects.active == cam)
        op = c_act.operator("markcam.pick_and_jump",
                            text="",
                            icon='RESTRICT_SELECT_OFF',
                            depress=is_active)
        op.object_name = cam.name
        op.frame = int(item.start)

class MARKCAM_OT_refresh(Operator):
    bl_idname = "markcam.refresh_from_scene"
    bl_label = "Refresh"
    bl_description = "Sort by start, fix overlaps, and sync list with markers (multiple occurrences supported)"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        sync_entries_from_scene(context.scene, cleanup=True)
        return {'FINISHED'}

class MARKCAM_PT_timeline(Panel):
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "MarkCam"
    bl_label = "Camera Ranges"

    @classmethod
    def poll(cls, context):
        return is_timeline_area(context)

    def draw(self, context):
        scn = context.scene
        lay = self.layout
        lay.use_property_split = False
        lay.use_property_decorate = False

        row = lay.row(align=True)
        row.operator("markcam.refresh_from_scene", icon="FILE_REFRESH", text="Refresh")

        h_name, h_start, h_end, h_act = _four_columns(lay)
        h_name.label(text="Camera")
        h_start.label(text="Start")
        h_end.label(text="End")
        h_act.label(text="")  # action

        lay.template_list("MARKCAM_UL_entries", "", scn, "markcam_entries",
                          scn, "markcam_entries_index", rows=7)

        lay.label(text="Hint: click name to rename camera.", icon='INFO')

# ---------- Header UI (next to Marker) ----------

def _draw_buttons_in_editor_menus(self, context):
    if not is_timeline_area(context):
        return
    layout = self.layout
    layout.separator(factor=0.4)
    row = layout.row(align=True)
    row.operator("qcm.camera_button", text="", icon='CAMERA_DATA')
    row.operator("qcm.remove_marker_at_current_frame", text="", icon='X')

# ---------- Registration ----------

classes = (
    QCM_OT_camera_button,
    QCM_OT_remove_marker_at_current_frame,
    MarkCamEntry,
    MARKCAM_OT_pick_and_jump,
    MARKCAM_UL_entries,
    MARKCAM_OT_refresh,
    MARKCAM_PT_timeline,
)

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

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.markcam_entries = CollectionProperty(type=MarkCamEntry)
    bpy.types.Scene.markcam_entries_index = IntProperty(default=0)
    bpy.types.Scene.markcam_updating = BoolProperty(default=False, options={'HIDDEN'})
    global _menu_targets
    _menu_targets = _try_hook_editor_menus()
    # Defer syncing until Blender is fully loaded to avoid AttributeError
    def _sync_all_scenes(dummy=None):
        for scn in bpy.data.scenes:
            sync_entries_from_scene(scn, cleanup=False)
        return None
    # Remove any previous handler to avoid duplicates
    for h in list(bpy.app.handlers.load_post):
        if getattr(h, "__name__", "") == "_sync_all_scenes":
            bpy.app.handlers.load_post.remove(h)
    bpy.app.handlers.load_post.append(_sync_all_scenes)

def unregister():
    _unhook_editor_menus()
    del bpy.types.Scene.markcam_entries
    del bpy.types.Scene.markcam_entries_index
    del bpy.types.Scene.markcam_updating
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()

