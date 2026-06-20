import math
import logging
import numpy as np

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMainWindow, QApplication, QWidget
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPainter, QColor

from gettext import gettext as _

log = logging.getLogger(__name__)

try:
    from OpenGL import GL
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False

QUALITY_CONFIGS = {
    "low":    dict(major=32,  minor=24,  shells=20, fur_len=0.06, tex_size=128),
    "medium": dict(major=64,  minor=48,  shells=40, fur_len=0.10, tex_size=256),
    "high":   dict(major=128, minor=96,  shells=70, fur_len=0.15, tex_size=512),
    "ultra":  dict(major=256, minor=192, shells=120, fur_len=0.22, tex_size=1024),
}

RESOLUTIONS = [
    "1280x720", "1600x900", "1920x1080",
    "2560x1440", "3200x1800", "3840x2160",
]

V_SRC = """
#version 330 core
layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec3 a_norm;
layout(location = 2) in vec2 a_uv;
uniform mat4 u_mvp;
uniform float u_shell;
uniform float u_shells;
uniform float u_fur_len;
out vec3 v_norm;
out vec2 v_uv;
out float v_alpha;
void main() {
    float layer = u_shell / u_shells;
    vec3 pos = a_pos + a_norm * u_fur_len * layer;
    v_norm = a_norm;
    v_uv = a_uv;
    v_alpha = 1.0 - layer;
    gl_Position = u_mvp * vec4(pos, 1.0);
}
"""

F_SRC = """
#version 330 core
in vec3 v_norm;
in vec2 v_uv;
in float v_alpha;
uniform sampler2D u_noise;
uniform vec3 u_color;
uniform vec3 u_light;
uniform float u_gloss;
out vec4 frag;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void main() {
    float d = texture(u_noise, v_uv * 8.0).r;
    float n = hash(v_uv + floor(v_alpha * 40.0));
    float a = v_alpha * d * (0.6 + 0.4 * n);
    if (a < 0.01) discard;
    vec3 N = normalize(v_norm);
    vec3 L = normalize(u_light);
    float diff = max(dot(N, L), 0.0);
    float amb = 0.25;
    vec3 c = u_color * (diff * 0.6 + amb) + 0.08;
    vec3 V = vec3(0.0, 0.0, 1.0);
    float rim = 1.0 - max(dot(N, V), 0.0);
    c += u_color * 0.3 * pow(rim, 4.0) * a;
    frag = vec4(c, a);
}
"""

B_V_SRC = """
#version 330 core
layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec3 a_norm;
layout(location = 2) in vec2 a_uv;
uniform mat4 u_mvp;
out vec3 v_norm;
out vec2 v_uv;
void main() {
    v_norm = a_norm;
    v_uv = a_uv;
    gl_Position = u_mvp * vec4(a_pos, 1.0);
}
"""

B_F_SRC = """
#version 330 core
in vec3 v_norm;
in vec2 v_uv;
uniform vec3 u_color;
uniform vec3 u_light;
uniform float u_gloss;
out vec4 frag;
void main() {
    vec3 N = normalize(v_norm);
    vec3 L = normalize(u_light);
    float diff = max(dot(N, L), 0.0);
    float amb = 0.2;
    vec3 V = vec3(0.0, 0.0, 1.0);
    vec3 H = normalize(L + V);
    float spec = pow(max(dot(N, H), 0.0), 32.0) * u_gloss;
    vec3 c = u_color * (diff * 0.7 + amb) + vec3(1.0) * spec * 0.5 + 0.05;
    frag = vec4(c, 1.0);
}
"""


def _cs(src, kind):
    s = GL.glCreateShader(kind)
    GL.glShaderSource(s, src)
    GL.glCompileShader(s)
    if not GL.glGetShaderiv(s, GL.GL_COMPILE_STATUS):
        raise RuntimeError(GL.glGetShaderInfoLog(s).decode())
    return s


def _link(vs, fs):
    p = GL.glCreateProgram()
    v = _cs(vs, GL.GL_VERTEX_SHADER)
    f = _cs(fs, GL.GL_FRAGMENT_SHADER)
    GL.glAttachShader(p, v)
    GL.glAttachShader(p, f)
    GL.glLinkProgram(p)
    if not GL.glGetProgramiv(p, GL.GL_LINK_STATUS):
        raise RuntimeError(GL.glGetProgramInfoLog(p).decode())
    GL.glDeleteShader(v)
    GL.glDeleteShader(f)
    return p


def _torus(major, minor):
    v, n, u, idx = [], [], [], []
    for i in range(major + 1):
        t = 2.0 * math.pi * i / major
        ct, st = math.cos(t), math.sin(t)
        for j in range(minor + 1):
            p = 2.0 * math.pi * j / minor
            cp, sp = math.cos(p), math.sin(p)
            r, R = 0.25, 0.80
            v += [(R + r*cp)*ct, r*sp, (R + r*cp)*st]
            n += [cp*ct, sp, cp*st]
            u += [i/major, j/minor]
    for i in range(major):
        for j in range(minor):
            a = i * (minor+1) + j
            b = a + minor + 1
            idx += [a, b, a+1, b, b+1, a+1]
    return v, n, u, idx


def _noise_tex(size):
    d = np.random.rand(size, size).astype(np.float32)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RED, size, size, 0,
                    GL.GL_RED, GL.GL_FLOAT, d.tobytes())


def _persp(fov, a, n, f):
    t = 1.0 / math.tan(math.radians(fov) / 2.0)
    d = n - f
    return np.array([[t/a, 0, 0, 0], [0, t, 0, 0],
                     [0, 0, (f+n)/d, 2*f*n/d], [0, 0, -1, 0]], dtype=np.float32)


def _look(eye, ctr, up):
    eye, ctr, up = [np.array(x, dtype=np.float32) for x in (eye, ctr, up)]
    f = ctr - eye
    fn = np.linalg.norm(f)
    f = f / fn if fn > 1e-8 else np.array([0, 0, -1], dtype=np.float32)
    s = np.cross(f, up)
    sn = np.linalg.norm(s)
    s = s / sn if sn > 1e-8 else np.array([1, 0, 0], dtype=np.float32)
    u = np.cross(s, f)
    return np.array([[s[0], s[1], s[2], -np.dot(s, eye)],
                     [u[0], u[1], u[2], -np.dot(u, eye)],
                     [-f[0], -f[1], -f[2], np.dot(f, eye)],
                     [0, 0, 0, 1]], dtype=np.float32)


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]], dtype=np.float32)


def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]], dtype=np.float32)


class GLStressWidget(QOpenGLWidget):
    def __init__(self, quality="medium", res_w=1920, res_h=1080, parent=None):
        super().__init__(parent)
        self._cfg = QUALITY_CONFIGS.get(quality, QUALITY_CONFIGS["medium"])
        self._res_w = res_w
        self._res_h = res_h
        self._quality_label = quality
        self._time = 0.0
        self._frame_count = 0
        self._fps = 0.0
        self._fps_timer = 0.0
        self._gpu_temp = 0.0
        self._gpu_name = ""
        self._gpu_load = 0.0
        self._backend = None
        self._vao = self._vbo = self._ebo = 0
        self._index_count = 0
        self._fur_prog = self._base_prog = 0
        self._noise_tex = 0
        self._initialized = False

    def set_monitoring(self, backend, gpu_name):
        self._backend = backend
        self._gpu_name = gpu_name or "GPU"

    def start(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def stop(self):
        if hasattr(self, '_timer') and self._timer:
            self._timer.stop()

    def _tick(self):
        self._time += 1.0 / 60.0
        self._frame_count += 1
        self._fps_timer += 1.0 / 60.0
        if self._fps_timer >= 1.0:
            self._fps = self._frame_count / self._fps_timer
            self._frame_count = 0
            self._fps_timer = 0.0
        if self._backend:
            try:
                s = self._backend.get_sensors(0)
                self._gpu_temp = s.temp_core
                self._gpu_load = s.utilization_pct
            except Exception:
                pass
        self.update()

    def initializeGL(self):
        if not HAS_OPENGL:
            return
        try:
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glDisable(GL.GL_CULL_FACE)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            GL.glClearColor(0.03, 0.03, 0.05, 1.0)

            verts, norms, uvs, idxs = _torus(self._cfg["major"], self._cfg["minor"])
            self._index_count = len(idxs)
            nv = len(verts) // 3
            stride = 8
            data = np.empty(nv * stride, dtype=np.float32)
            for i in range(nv):
                data[i*stride+0: i*stride+3] = verts[i*3:i*3+3]
                data[i*stride+3: i*stride+6] = norms[i*3:i*3+3]
                data[i*stride+6: i*stride+8] = uvs[i*2:i*2+2]
            idx_a = np.array(idxs, dtype=np.uint32)

            self._vao = GL.glGenVertexArrays(1)
            GL.glBindVertexArray(self._vao)
            self._vbo = GL.glGenBuffers(1)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STATIC_DRAW)
            self._ebo = GL.glGenBuffers(1)
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self._ebo)
            GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, idx_a.nbytes, idx_a, GL.GL_STATIC_DRAW)

            sb = stride * 4
            GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, sb, GL.ctypes.c_void_p(0))
            GL.glEnableVertexAttribArray(0)
            GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, sb, GL.ctypes.c_void_p(12))
            GL.glEnableVertexAttribArray(1)
            GL.glVertexAttribPointer(2, 2, GL.GL_FLOAT, GL.GL_FALSE, sb, GL.ctypes.c_void_p(24))
            GL.glEnableVertexAttribArray(2)

            self._fur_prog = _link(V_SRC, F_SRC)
            self._base_prog = _link(B_V_SRC, B_F_SRC)

            self._noise_tex = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._noise_tex)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_REPEAT)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            _noise_tex(self._cfg["tex_size"])

            self._initialized = True
            log.info("GL stress OK (%s)", self._quality_label)
        except Exception as e:
            log.error("GL init: %s", e, exc_info=True)

    def paintGL(self):
        if not self._initialized:
            return
        try:
            w = max(self.width(), 1)
            h = max(self.height(), 1)
            dpr = self.devicePixelRatio()
            GL.glViewport(0, 0, int(w * dpr), int(h * dpr))
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

            aspect = w / h
            rot = self._time * 0.4
            mvp = _persp(45, aspect, 0.1, 10) @ _look([4.0, 2.5, 4.0], [0, 0, 0], [0, 1, 0]) @ _ry(rot) @ _rx(rot * 0.08)
            mvp_f = mvp.flatten()
            light = np.array([0.5, 0.7, 0.6], dtype=np.float32)
            base_col = np.array([0.78, 0.48, 0.12], dtype=np.float32)
            shells = self._cfg["shells"]

            GL.glUseProgram(self._base_prog)
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._base_prog, "u_mvp"), 1, GL.GL_FALSE, mvp_f)
            GL.glUniform3fv(GL.glGetUniformLocation(self._base_prog, "u_color"), 1, base_col)
            GL.glUniform3fv(GL.glGetUniformLocation(self._base_prog, "u_light"), 1, light)
            GL.glUniform1f(GL.glGetUniformLocation(self._base_prog, "u_gloss"), 0.6)
            GL.glBindVertexArray(self._vao)
            GL.glDrawElements(GL.GL_TRIANGLES, self._index_count, GL.GL_UNSIGNED_INT, None)

            GL.glUseProgram(self._fur_prog)
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._fur_prog, "u_mvp"), 1, GL.GL_FALSE, mvp_f)
            GL.glUniform3fv(GL.glGetUniformLocation(self._fur_prog, "u_color"), 1, base_col + 0.15)
            GL.glUniform3fv(GL.glGetUniformLocation(self._fur_prog, "u_light"), 1, light)
            GL.glUniform1f(GL.glGetUniformLocation(self._fur_prog, "u_shells"), float(shells))
            GL.glUniform1f(GL.glGetUniformLocation(self._fur_prog, "u_fur_len"), self._cfg["fur_len"])
            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._noise_tex)
            GL.glUniform1i(GL.glGetUniformLocation(self._fur_prog, "u_noise"), 0)

            GL.glEnable(GL.GL_BLEND)
            GL.glDepthMask(GL.GL_FALSE)
            for shell in range(shells):
                GL.glUniform1f(GL.glGetUniformLocation(self._fur_prog, "u_shell"), float(shell))
                GL.glDrawElements(GL.GL_TRIANGLES, self._index_count, GL.GL_UNSIGNED_INT, None)
            GL.glDepthMask(GL.GL_TRUE)
            GL.glDisable(GL.GL_BLEND)

        except Exception as e:
            log.error("GL render: %s", e, exc_info=True)

    def resizeGL(self, w, h):
        if HAS_OPENGL:
            GL.glViewport(0, 0, int(w * self.devicePixelRatio()), int(h * self.devicePixelRatio()))


class Overlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._lines = []

    def set_lines(self, lines):
        self._lines = list(lines)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        f = QFont("Consolas, monospace", 13)
        f.setStyleHint(QFont.Monospace)
        p.setFont(f)
        p.setPen(QColor(180, 220, 255, 230))
        y = self.height() - 16
        for line in reversed(self._lines):
            r = p.fontMetrics().boundingRect(line)
            y -= r.height() + 4
            p.fillRect(8, y, r.width() + 8, r.height() + 4, QColor(0, 0, 0, 140))
            p.drawText(10, y + r.height() - 2, line)
        p.end()


class GLStressWindow(QMainWindow):
    closed = Signal()

    def __init__(self, quality, res_w, res_h, backend, gpu_name):
        super().__init__()
        self.setWindowTitle("GPUForge Stress Test")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setCursor(Qt.BlankCursor)

        self._gl = GLStressWidget(quality, res_w, res_h)
        self._gl.set_monitoring(backend, gpu_name)
        self.setCentralWidget(self._gl)

        self._overlay = Overlay(self._gl)
        self._res_w = res_w
        self._res_h = res_h
        self._quality_label = quality
        self._fps = 0.0

        screen = QApplication.primaryScreen()
        geo = screen.geometry()
        self.resize(geo.width(), geo.height())
        self.move(geo.x(), geo.y())
        self.showFullScreen()

        self._overlay.resize(self._gl.size())
        self._gl.start()

        self._info = QTimer(self)
        self._info.timeout.connect(self._update_overlay)
        self._info.start(250)

    def _update_overlay(self):
        self._overlay.set_lines([
            f"GPU: {self._gl._gpu_name}",
            f"Temp: {self._gl._gpu_temp:.0f}C  Load: {self._gl._gpu_load:.0f}%",
            f"FPS: {self._gl._fps:.1f}",
            f"Shaders: {self._gl._cfg['shells']}  Quality: {self._quality_label}",
            f"{self._res_w}x{self._res_h}  |  ESC to exit",
        ])
        self._overlay.resize(self._gl.size())
        self._fps = self._gl._fps

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self._gl.stop()
        self._info.stop()
        self.closed.emit()
        super().closeEvent(event)

    @property
    def fps(self):
        return self._fps
