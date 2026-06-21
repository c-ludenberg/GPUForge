import logging
import numpy as np

log = logging.getLogger(__name__)

GROUP_COLORS = {
    "CERAMIKA": (0.92, 0.90, 0.85),
    "ZBIORNIK": (0.92, 0.90, 0.85),
    "DESKA": (0.60, 0.50, 0.40),
    "CHROM": (0.75, 0.75, 0.78),
    "default": (0.85, 0.82, 0.78),
}


def _group_color(name):
    upper = name.upper()
    for key in GROUP_COLORS:
        if key in upper:
            return GROUP_COLORS[key]
    return GROUP_COLORS["default"]


def _center_and_scale(verts):
    if len(verts) == 0:
        return verts
    mn = verts.min(axis=0)
    mx = verts.max(axis=0)
    center = (mn + mx) / 2.0
    size = max(mx - mn) or 1.0
    scale = 1.8 / size
    return (verts - center) * scale


def load_obj(path):
    try:
        import trimesh
    except ImportError:
        log.error("trimesh not installed")
        return [], [], [], [], []

    try:
        scene = trimesh.load(path)
    except Exception as e:
        log.error("trimesh load failed: %s", e)
        return [], [], [], [], []

    if isinstance(scene, trimesh.Scene):
        meshes = list(scene.geometry.items())
    else:
        meshes = [("default", scene)]

    all_verts = []
    all_norms = []
    all_uvs = []
    all_cols = []
    all_idx = []
    base = 0

    for name, mesh in meshes:
        if not isinstance(mesh, trimesh.Trimesh):
            continue
        verts = mesh.vertices
        if len(verts) == 0:
            continue
        faces = mesh.faces
        norms = mesh.vertex_normals
        color = _group_color(str(name))

        uv = None
        if hasattr(mesh.visual, "uv") and mesh.visual.uv is not None:
            uv = mesh.visual.uv
        elif hasattr(mesh, "_uvs") and mesh._uvs is not None:
            uv = mesh._uvs
        if uv is None or len(uv) != len(verts):
            uv = np.zeros((len(verts), 2), dtype=np.float32)

        idx = faces.flatten().astype(np.int32) + base
        base += len(verts)

        all_verts.append(verts)
        all_norms.append(norms)
        all_uvs.append(uv)
        col = np.full((len(verts), 3), color, dtype=np.float32)
        all_cols.append(col)
        all_idx.append(idx)

    if not all_verts:
        return [], [], [], [], []

    verts = np.vstack(all_verts)
    norms = np.vstack(all_norms)
    uvs = np.vstack(all_uvs)
    cols = np.vstack(all_cols)
    idx = np.hstack(all_idx)

    verts = _center_and_scale(verts)

    return verts.flatten().tolist(), norms.flatten().tolist(), uvs.flatten().tolist(), cols.flatten().tolist(), idx.tolist()
