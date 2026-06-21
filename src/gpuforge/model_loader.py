import math
import logging
from collections import defaultdict

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


def load_obj(path):
    # Raw OBJ data
    positions = []
    texcoords = []
    raw_faces = []  # list of (v_idx, vt_idx) per face, group_color

    current_group = "default"
    base_color = GROUP_COLORS["default"]

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("usemtl"):
                continue
            if line.startswith("g "):
                current_group = line[2:].strip()
                base_color = _group_color(current_group)
                continue
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "v":
                positions.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif parts[0] == "vt":
                texcoords.append((float(parts[1]), float(parts[2])))
            elif parts[0] == "f":
                face = []
                for p in parts[1:]:
                    tokens = p.split("/")
                    vi = int(tokens[0]) - 1
                    ti = int(tokens[1]) - 1 if len(tokens) > 1 and tokens[1] else -1
                    face.append((vi, ti))
                raw_faces.append((face, base_color))

    # Build unique (pos_idx, uv_idx) → new vertex index
    unique_map = {}
    out_verts = []
    out_norms = []
    out_uvs = []
    out_cols = []
    out_idxs = []

    # First pass: create unique vertices and compute per-vertex normal accumulators
    normal_acc = defaultdict(lambda: [0.0, 0.0, 0.0])
    face_normals = []

    for face, color in raw_faces:
        if len(face) < 3:
            continue
        # Compute face normal via Newell's method
        fnx = fny = fnz = 0.0
        for i in range(len(face)):
            x1, y1, z1 = positions[face[i][0]]
            x2, y2, z2 = positions[face[(i + 1) % len(face)][0]]
            fnx += (y1 - y2) * (z1 + z2)
            fny += (z1 - z2) * (x1 + x2)
            fnz += (x1 - x2) * (y1 + y2)
        fl = math.sqrt(fnx * fnx + fny * fny + fnz * fnz) or 1.0
        fnx /= fl
        fny /= fl
        fnz /= fl
        face_normals.append((fnx, fny, fnz))

        # Triangulate
        for i in range(1, len(face) - 1):
            tri = [face[0], face[i], face[i + 1]]
            for v_idx, vt_idx in tri:
                key = (v_idx, vt_idx)
                if key not in unique_map:
                    unique_map[key] = len(out_verts)
                    out_verts.append(positions[v_idx])
                    out_norms.append([fnx, fny, fnz])
                    out_uvs.append(texcoords[vt_idx] if 0 <= vt_idx < len(texcoords) else (0.0, 0.0))
                    out_cols.append(color)
                else:
                    # Accumulate normal for averaging
                    ni = unique_map[key]
                    n = out_norms[ni]
                    n[0] += fnx
                    n[1] += fny
                    n[2] += fnz
                out_idxs.append(unique_map[key])

    # Normalize accumulated normals
    for n in out_norms:
        nl = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) or 1.0
        n[0] /= nl
        n[1] /= nl
        n[2] /= nl

    # Flatten to lists
    v = [c for p in out_verts for c in p]
    n = [c for p in out_norms for c in p]
    u = [c for p in out_uvs for c in p]
    c = [ch for col in out_cols for ch in col]
    idx = out_idxs

    # Center and normalize to unit sphere
    nv = len(v) // 3
    if nv > 0:
        minx = min(v[i * 3] for i in range(nv))
        maxx = max(v[i * 3] for i in range(nv))
        miny = min(v[i * 3 + 1] for i in range(nv))
        maxy = max(v[i * 3 + 1] for i in range(nv))
        minz = min(v[i * 3 + 2] for i in range(nv))
        maxz = max(v[i * 3 + 2] for i in range(nv))
        cx = (minx + maxx) / 2.0
        cy = (miny + maxy) / 2.0
        cz = (minz + maxz) / 2.0
        s = max(maxx - minx, maxy - miny, maxz - minz) or 1.0
        s = 1.8 / s
        for i in range(nv):
            v[i * 3] = (v[i * 3] - cx) * s
            v[i * 3 + 1] = (v[i * 3 + 1] - cy) * s
            v[i * 3 + 2] = (v[i * 3 + 2] - cz) * s

    return v, n, u, c, idx


def generate_torus_knot(p=3, q=2, major_seg=128, minor_seg=32, radius=1.0, tube=0.35):
    verts = []
    idxs = []
    for i in range(major_seg + 1):
        t = 2.0 * math.pi * i / major_seg
        r = math.cos(q * t) * radius + 2.0
        cx = math.cos(p * t) * r
        cy = math.sin(p * t) * r
        cz = -math.sin(q * t) * radius * 0.5
        for j in range(minor_seg + 1):
            u = 2.0 * math.pi * j / minor_seg
            nxn = math.cos(p * t) * math.cos(q * t) * radius
            nyn = math.sin(p * t) * math.cos(q * t) * radius
            nzn = math.sin(q * t) * radius * 0.5
            nl = math.sqrt(nxn * nxn + nyn * nyn + nzn * nzn) or 1
            nx, ny, nz = nxn / nl, nyn / nl, nzn / nl
            tx = -p * math.sin(p * t) * r + math.cos(p * t) * (-q * math.sin(q * t) * radius)
            ty = p * math.cos(p * t) * r + math.sin(p * t) * (-q * math.sin(q * t) * radius)
            tz = -q * math.cos(q * t) * radius * 0.5
            tl = math.sqrt(tx * tx + ty * ty + tz * tz) or 1
            bx = (ty * nz - tz * ny) / tl
            by = (tz * nx - tx * nz) / tl
            bz = (tx * ny - ty * nx) / tl
            rx = nx * math.cos(u) + bx * math.sin(u)
            ry = ny * math.cos(u) + by * math.sin(u)
            rz = nz * math.cos(u) + bz * math.sin(u)
            verts.append((cx + rx * tube, cy + ry * tube, cz + rz * tube))

    for i in range(major_seg):
        for j in range(minor_seg):
            a = i * (minor_seg + 1) + j
            b = a + minor_seg + 1
            idxs.extend([a, b, a + 1, b, b + 1, a + 1])

    tris = [verts[i] for i in idxs]
    col = (0.78, 0.48, 0.12)
    cols = [col] * len(tris)
    return tris, cols, False
