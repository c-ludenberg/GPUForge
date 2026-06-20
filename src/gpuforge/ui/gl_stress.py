import math
import logging
import numpy as np

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMainWindow, QApplication, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPainter, QColor, QPalette

from gettext import gettext as _

log = logging.getLogger(__name__)

try:
    from OpenGL import GL
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False
    log.warning("PyOpenGL not installed")


QUALITY_CONFIGS = {
    "low":    dict(major=32,  minor=24,  shells=30,  fur_len=0.10, tex_size=128),
    "medium": dict(major=64,  minor=48,  shells=60,  fur_len=0.18, tex_size=256),
    "high":   dict(major=128, minor=96,  shells=120, fur_len=0.25, tex_size=512),
    "ultra":  dict(major=256, minor=192, shells=200, fur_len=0.35, tex_size=1024),
}

RESOLUTIONS = [
    "1280x720", "1600x900", "1920x1080",
    "2560x1440", "3200x1800", "3840x2160",
]

FUR_VERT = """
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

FUR_FRAG = """
#version 330 core
in vec3 v_norm;
in vec2 v_uv;
in float v_alpha;

uniform sampler2D u_noise;
uniform vec3 u_color;
uniform vec3 u_light;

out vec4 frag;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void main() {
    float d = texture(u_noise, v_uv * 6.0).r;
    float n = hash(v_uv + floor(v_alpha * 60.0));
    float a = v_alpha * d * (0.75 + 0.25 * n);
    if (a < 0.005) discard;

    vec3 N = normalize(v_norm);
    vec3 L = normalize(u_light);
    float diff = max(dot(N, L), 0.0);
    float amb = 0.2;
    vec3 c = u_color * (diff * 0.65 + amb) + 0.06;

    vec3 V = vec3(0.0, 0.0, 1.0);
    float rim = 1.0 - max(dot(N, V), 0.0);
    c += vec3(0.25, 0.12, 0.04) * pow(rim, 3.0) * a;

    frag = vec4(c, a);
}
"""

TORUS_VERT = """
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

TORUS_FRAG = """
#version 330 core
in vec3 v_norm;
in vec2 v_uv;

uniform vec3 u_color;
uniform vec3 u_light;

out vec4 frag;

void main() {
    vec3 N = normalize(v_norm);
    vec3 L = normalize(u_light);
    float diff = max(dot(N, L), 0.0);
    float amb = 0.15;
    vec3 c = u_color * (diff * 0.7 + amb) + 0.05;
    frag = vec4(c, 1.0);
}
"""


def _compile_shader(src, kind):
    shader = GL.glCreateShader(kind)
    GL.glShaderSource(shader, src)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        err = GL.glGetShaderInfoLog(shader).decode()
        log.error("Shader compile error: %s", err)
        raise RuntimeError(f"Shader compile error: {err}")
    return shader


def _link_program(vsrc, fsrc):
    prog = GL.glCreateProgram()
    vs = _compile_shader(vsrc, GL.GL_VERTEX_SHADER)
    fs = _compile_shader(fsrc, GL.GL_FRAGMENT_SHADER)
    GL.glAttachShader(prog, vs)
    GL.glAttachShader(prog, fs)
    GL.glLinkProgram(prog)
    if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
        err = GL.glGetProgramInfoLog(prog).decode()
        log.error("Program link error: %s", err)
        raise RuntimeError(f"Program link error: {err}")
    GL.glDeleteShader(vs)
    GL.glDeleteShader(fs)
    return prog


def _gen_torus(major, minor):
    verts, norms, uvs, idxs = [], [], [], []
    for i in range(major + 1):
        theta = 2.0 * math.pi * i / major
        ct, st = math.cos(theta), math.sin(theta)
        for j in range(minor + 1):
            phi = 2.0 * math.pi * j / minor
            cp, sp = math.cos(phi), math.sin(phi)
            r, R = 0.35, 0.8
            verts += [R * ct + r * cp * ct, r * sp, R * st + r * cp * st]
            norms += [cp * ct, sp, cp * st]
            uvs += [i / major, j / minor]
    for i in range(major):
        for j in range(minor):
            a = i * (minor + 1) + j
            b = a + minor + 1
            idxs += [a, b, a + 1, b, b + 1, a + 1]
    return verts, norms, uvs, idxs


def _gen_noise_tex(size):
    noise = np.random.rand(size, size).astype(np.float32)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RED, size, size, 0,
                    GL.GL_RED, GL.GL_FLOAT, noise.tobytes())


def _perspective(fov, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fov) / 2.0)
    d = near - far
    return np.array([
        [f / aspect, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, (far + near) / d, 2 * far * near / d],
        [0, 0, -1, 0],
    ], dtype=np.float32)


def _look_at(eye, center, up):
    eye = np.array(eye, dtype=np.float32)
    center = np.array(center, dtype=np.float32)
    up = np.array(up, dtype=np.float32)
    f = center - eye
    fn = np.linalg.norm(f)
    f = f / fn if fn > 1e-8 else np.array([0.0, 0.0, -1.0], dtype=np.float32)
    s = np.cross(f, up)
    sn = np.linalg.norm(s)
    s = s / sn if sn > 1e-8 else np.array([1.0, 0.0, 0.0], dtype=np.float32)
    u = np.cross(s, f)
    return np.array([
        [s[0], s[1], s[2], -np.dot(s, eye)],
        [u[0], u[1], u[2], -np.dot(u, eye)],
        [-f[0], -f[1], -f[2], np.dot(f, eye)],
        [0, 0, 0, 1],
    ], dtype=np.float32)


def _rotate_y(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]], dtype=np.float32)


def _rotate_x(angle):
    c, s = math.cos(angle), math.sin(angle)
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
        pass  # timer managed by GLStressWindow

    def stop(self):
        pass

    def initializeGL(self):
        if not HAS_OPENGL:
            return
        try:
            self._do_init()
        except Exception as e:
            log.error("GL init failed: %s", e, exc_info=True)

    def _do_init(self):
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glClearColor(0.035, 0.035, 0.055, 1.0)

        verts, norms, uvs, idxs = _gen_torus(self._cfg["major"], self._cfg["minor"])
        self._index_count = len(idxs)
        n_verts = len(verts) // 3

        stride = 8
        data = np.empty(n_verts * stride, dtype=np.float32)
        for i in range(n_verts):
            data[i * stride + 0] = verts[i * 3 + 0]
            data[i * stride + 1] = verts[i * 3 + 1]
            data[i * stride + 2] = verts[i * 3 + 2]
            data[i * stride + 3] = norms[i * 3 + 0]
            data[i * stride + 4] = norms[i * 3 + 1]
            data[i * stride + 5] = norms[i * 3 + 2]
            data[i * stride + 6] = uvs[i * 2 + 0]
            data[i * stride + 7] = uvs[i * 2 + 1]

        idx_arr = np.array(idxs, dtype=np.uint32)

        self._vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self._vao)

        self._vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STATIC_DRAW)

        self._ebo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self._ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, idx_arr.nbytes, idx_arr, GL.GL_STATIC_DRAW)

        stride_bytes = stride * 4
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride_bytes, GL.ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride_bytes, GL.ctypes.c_void_p(12))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(2, 2, GL.GL_FLOAT, GL.GL_FALSE, stride_bytes, GL.ctypes.c_void_p(24))
        GL.glEnableVertexAttribArray(2)

        self._fur_prog = _link_program(FUR_VERT, FUR_FRAG)
        self._base_prog = _link_program(TORUS_VERT, TORUS_FRAG)

        self._noise_tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._noise_tex)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_REPEAT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        _gen_noise_tex(self._cfg["tex_size"])

        self._initialized = True
        log.info("GL stress init OK (%s, %d shells)", self._quality_label, self._cfg["shells"])

    def paintGL(self):
        if not self._initialized:
            return
        try:
            w = max(self.width(), 1)
            h = max(self.height(), 1)
            aspect = w / h

            GL.glViewport(0, 0, int(w * self.devicePixelRatio()), int(h * self.devicePixelRatio()))
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

            rot = self._time * 0.35
            mvp = _perspective(50.0, aspect, 0.1, 10.0) @ _look_at([2.4, 1.5, 3.0], [0, 0, 0], [0, 1, 0]) @ _rotate_y(rot) @ _rotate_x(rot * 0.12)
            mvp_f = mvp.flatten()
            light = np.array([0.6, 0.85, 0.7], dtype=np.float32)
            color = np.array([0.82, 0.52, 0.18], dtype=np.float32)
            shells = self._cfg["shells"]

            GL.glUseProgram(self._fur_prog)
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._fur_prog, "u_mvp"), 1, GL.GL_FALSE, mvp_f)
            GL.glUniform3fv(GL.glGetUniformLocation(self._fur_prog, "u_color"), 1, color)
            GL.glUniform3fv(GL.glGetUniformLocation(self._fur_prog, "u_light"), 1, light)
            GL.glUniform1f(GL.glGetUniformLocation(self._fur_prog, "u_shells"), float(shells))
            GL.glUniform1f(GL.glGetUniformLocation(self._fur_prog, "u_fur_len"), self._cfg["fur_len"])

            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._noise_tex)
            GL.glUniform1i(GL.glGetUniformLocation(self._fur_prog, "u_noise"), 0)

            GL.glBindVertexArray(self._vao)
            GL.glEnable(GL.GL_BLEND)
            GL.glDepthMask(GL.GL_FALSE)
            for shell in range(shells):
                GL.glUniform1f(GL.glGetUniformLocation(self._fur_prog, "u_shell"), float(shell))
                GL.glDrawElements(GL.GL_TRIANGLES, self._index_count, GL.GL_UNSIGNED_INT, None)

            GL.glDepthMask(GL.GL_TRUE)
            GL.glDisable(GL.GL_BLEND)

            GL.glUseProgram(self._base_prog)
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._base_prog, "u_mvp"), 1, GL.GL_FALSE, mvp_f)
            GL.glUniform3fv(GL.glGetUniformLocation(self._base_prog, "u_color"), 1, color * 0.65)
            GL.glUniform3fv(GL.glGetUniformLocation(self._base_prog, "u_light"), 1, light)
            GL.glDrawElements(GL.GL_TRIANGLES, self._index_count, GL.GL_UNSIGNED_INT, None)

        except Exception as e:
            log.error("GL render error: %s", e, exc_info=True)

    def resizeGL(self, w, h):
        if HAS_OPENGL:
            GL.glViewport(0, 0, int(w * self.devicePixelRatio()), int(h * self.devicePixelRatio()))


class Overlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self._lines = []

    def set_lines(self, lines):
        self._lines = lines
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = QFont("Consolas, monospace", 13)
        font.setStyleHint(QFont.Monospace)
        painter.setFont(font)
        painter.setPen(QColor(180, 220, 255, 230))

        y = self.height() - 16
        for line in reversed(self._lines):
            rect = painter.fontMetrics().boundingRect(line)
            y -= rect.height() + 4
            painter.fillRect(8, y, rect.width() + 8, rect.height() + 4, QColor(0, 0, 0, 140))
            painter.drawText(10, y + rect.height() - 2, line)


class GLStressWindow(QMainWindow):
    closed = Signal()

    def __init__(self, quality, res_w, res_h, backend, gpu_name):
        super().__init__()
        self.setWindowTitle(_("GPUForge Stress Test"))
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setCursor(Qt.BlankCursor)

        self._gl = GLStressWidget(quality, res_w, res_h)
        self._gl.set_monitoring(backend, gpu_name)
        self.setCentralWidget(self._gl)

        self._overlay = Overlay(self._gl)
        self._overlay.resize(self._gl.size())

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

        self._info_timer = QTimer(self)
        self._info_timer.timeout.connect(self._update_overlay)
        self._info_timer.start(250)

    def _update_overlay(self):
        lines = [
            f"GPU: {self._gl._gpu_name}",
            f"Temp: {self._gl._gpu_temp:.0f}°C  Load: {self._gl._gpu_load:.0f}%",
            f"FPS: {self._gl._fps:.1f}",
            f"Shells: {self._gl._cfg['shells']}  Quality: {self._quality_label}",
            f"{self._res_w}x{self._res_h}  |  ESC to exit",
        ]
        self._overlay.set_lines(lines)
        self._overlay.resize(self._gl.size())
        self._fps = self._gl._fps

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self._gl.stop()
        self._info_timer.stop()
        self.closed.emit()
        super().closeEvent(event)

    @property
    def fps(self):
        return self._fps
