# MarkCam — Camera & Marker Tools for Blender

**MarkCam** adds two quick-action buttons to the Timeline header (Dope Sheet → `Timeline`) and a compact **Camera Ranges** panel for easier camera + marker control.

---

## ✨ Features

- **Click** 🎥 Bind **active camera** to a marker at the **current frame**  
- **Shift + Click** 🎥 Create a **new camera** from your **current 3D view** (no marker)  
- **Ctrl + Click** 🎥 Create a **new camera** from view **and** bind a marker at the current frame  
- **Click X** ❌ Remove **marker(s)** at the current frame (never deletes cameras)  
- **Ctrl + Click X** ❌ Remove **ALL** markers **(with confirmation)**

**Camera Ranges (N-panel, Timeline):**
- One row **per camera-bound marker** (you can reuse the **same camera** multiple times)
- **Camera** (inline rename) · **Start** (editable; live moves the marker) · **End** (auto to the next start or scene end) · **Select/Jump** (selects the camera and moves the playhead)  
- **Refresh** 🔁 Sorts by start and resolves overlaps

---

## 🧭 Where it works
- Only in **Dope Sheet → Timeline** mode  
- Designed for speed: **click / Shift-click / Ctrl-click** — no menus

---

## 📦 Installation
- From Blender: **Edit → Preferences → Extensions**, search **“MarkCam”** and install  
- **Drag & drop** the `.zip` into the Blender window  
- Or: **Edit → Preferences → Add-ons → Install**, pick the `.zip`

---

**Requires:** Blender 4.5+  

**Support the project:** https://somrender.gumroad.com/l/ddcyp  
**Bugs / requests:** https://github.com/Somrender/MarkCam/issues
