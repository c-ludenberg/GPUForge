import math
import struct
import logging
import numpy as np

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMainWindow, QLabel, QApplication
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPainter, QColor

from gettext import gettext as _

log = logging.getLogger(__name__)

try:
    from OpenGL import GL
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False
    log.warning("PyOpenGL not installed — stress test will use software fallback")


QUALITY_CONFIGS = {
    "low":    dict(major=48,  minor=24,  shells=40,  fur_len=0.12, tex_size=128),
    "medium": dict(major=96,  minor=48,  shells=80,  fur_len=0.20, tex_size=256),
    "high":   dict(major=192, minor=96,  shells=160, fur_len=0.30, tex_size=512),
    "ultra":  dict(major=384, minor=192, shells=300, fur_len=0.40, tex_size=1024),
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
uniform float u_time;

out vec3 v_norm;
out vec2 v_uv;
out float v_alpha;

void main() {
    float layer = u_shell / u_shells;
    vec3 disp = a_norm * u_fur_len * layer;
    vec3 pos = a_pos + disp + a_norm * sin(u_time + a_pos.x * 10.0 + a_pos.z * 7.0) * 0.005 * layer;
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
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

void main() {
    float d = texture(u_noise, v_uv * 6.0).r;
    float n = hash(v_uv + floor(v_alpha * 60.0));
    float a = v_alpha * d * (0.8 + 0.2 * n);
    if (a < 0.01) discard;

    vec3 N = normalize(v_norm);
    vec3 L = normalize(u_light);
    float diff = max(dot(N, L), 0.0);
    float amb = 0.18;
    vec3 c = u_color * (diff * 0.7 + amb) + vec3(0.08);

    // Rim light for fur look
    vec3 V = vec3(0.0, 0.0, 1.0);
    float rim = 1.0 - max(dot(N, V), 0.0);
    c += vec3(0.3, 0.15, 0.05) * pow(rim, 3.0) * a;

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
    vec3 c = u_color * (diff * 0.7 + amb) + vec3(0.05);
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
            r = 1.0 + 0.4 * cp
            verts.extend([r * ct, 0.4 * sp, r * st])
            norms.extend([cp * ct, sp, cp * st])
            uvs.extend([i / major, j / minor])
    for i in range(major):
        for j in range(minor):
            a = i * (minor + 1) + j
            b = a + minor + 1
            idxs.extend([a, b, a + 1, b, b + 1, a + 1])
    return verts, norms, uvs, idxs


def _gen_noise_tex(size):
    noise = np.random.rand(size, size).astype(np.float32)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_R32F, size, size, 0,
                    GL.GL_RED, GL.GL_FLOAT, noise.tobytes())


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

        self._vao = self._vbo = self._ebo = None
        self._index_count = 0
        self._fur_prog = self._base_prog = None
        self._noise_tex = None
        self._initialized = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setTimerType(Qt.PreciseTimer)

    def set_monitoring(self, backend, gpu_name):
        self._backend = backend
        self._gpu_name = gpu_name
        if not gpu_name:
            import platform
            self._gpu_name = platform.node()

    @property
    def fps(self):
        return self._fps

    def start(self):
        self._timer.start(16)

    def stop(self):
        self._timer.stop()

    def _tick(self):
        dt = 1.0 / 60.0
        self._time += dt
        self._frame_count += 1
        self._fps_timer += dt
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
            self._initialized = False
            return

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glClearColor(0.04, 0.04, 0.06, 1.0)

        verts, norms, uvs, idxs = _gen_torus(self._cfg["major"], self._cfg["minor"])
        self._index_count = len(idxs)

        vert_data = np.array(verts, dtype=np.float32)
        norm_data = np.array(norms, dtype=np.float32)
        uv_data = np.array(uvs, dtype=np.float32)
        idx_data = np.array(idxs, dtype=np.uint32)

        stride = 3 + 3 + 2
        interleaved = np.empty(len(verts) // 3 * stride, dtype=np.float32)
        interleaved[0::stride] = vert_data[0::3]
        interleaved[1::stride] = vert_data[1::3]
        interleaved[2::stride] = vert_data[2::3]
        interleaved[3::stride] = norm_data[0::3]
        interleaved[4::stride] = norm_data[1::3]
        interleaved[5::stride] = norm_data[2::3]
        interleaved[6::stride] = uv_data[0::2]
        interleaved[7::stride] = uv_data[1::2]

        self._vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self._vao)

        self._vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, interleaved.nbytes,
                        interleaved.tobytes(), GL.GL_STATIC_DRAW)

        self._ebo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self._ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, idx_data.nbytes,
                        idx_data.tobytes(), GL.GL_STATIC_DRAW)

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

    def paintGL(self):
        if not self._initialized:
            self._draw_fallback()
            return

        w = self.width() * self.devicePixelRatio()
        h = self.height() * self.devicePixelRatio()
        aspect = w / h

        GL.glViewport(0, 0, int(w), int(h))
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        rot = self._time * 0.3

        proj = self._perspective(45.0, aspect, 0.1, 10.0)
        view = self._look_at([2.2, 1.2, 2.8], [0, 0, 0], [0, 1, 0])
        model = self._rotate_y(rot) @ self._rotate_x(rot * 0.15)
        mvp = proj @ view @ model

        mvp_f = np.array(mvp, dtype=np.float32).flatten()

        light = np.array([0.5, 0.8, 0.6], dtype=np.float32)
        color = np.array([0.85, 0.55, 0.20], dtype=np.float32)

        shells = self._cfg["shells"]
        fur_len = self._cfg["fur_len"]

        GL.glUseProgram(self._fur_prog)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._fur_prog, "u_mvp"), 1, GL.GL_FALSE, mvp_f)
        GL.glUniform3fv(GL.glGetUniformLocation(self._fur_prog, "u_color"), 1, color)
        GL.glUniform3fv(GL.glGetUniformLocation(self._fur_prog, "u_light"), 1, light)
        GL.glUniform1f(GL.glGetUniformLocation(self._fur_prog, "u_time"), self._time)
        GL.glUniform1f(GL.glGetUniformLocation(self._fur_prog, "u_shells"), float(shells))
        GL.glUniform1f(GL.glGetUniformLocation(self._fur_prog, "u_fur_len"), fur_len)

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
        GL.glUniform3fv(GL.glGetUniformLocation(self._base_prog, "u_color"), 1, color * 0.7)
        GL.glUniform3fv(GL.glGetUniformLocation(self._base_prog, "u_light"), 1, light)
        GL.glDrawElements(GL.GL_TRIANGLES, self._index_count, GL.GL_UNSIGNED_INT, None)

        self._draw_overlay(w, h)

    def _draw_overlay(self, vp_w, vp_h):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)

        font_specs = QFont("Consolas, monospace", 13)
        font_specs.setStyleHint(QFont.Monospace)
        painter.setFont(font_specs)

        painter.setPen(QColor(180, 220, 255, 230))

        stats = [
            f"GPU: {self._gpu_name}",
            f"Temp: {self._gpu_temp:.0f}°C",
            f"FPS: {self._fps:.1f}",
            f"Shells: {self._cfg['shells']}",
            f"Quality: {self._quality_label}",
        ]
        x = 16
        y = vp_h / self.devicePixelRatio() - 16
        for line in reversed(stats):
            rect = painter.fontMetrics().boundingRect(line)
            y -= rect.height() + 4
            painter.fillRect(x - 4, y, rect.width() + 8, rect.height() + 4,
                             QColor(0, 0, 0, 140))
            painter.drawText(x, y + rect.height() - 2, line)

        info_line = f"{self._res_w}x{self._res_h}  |  {self._quality_label}  |  Press ESC to exit"
        painter.setPen(QColor(255, 255, 255, 200))
        font_info = QFont("Consolas, monospace", 12)
        painter.setFont(font_info)
        ir = painter.fontMetrics().boundingRect(info_line)
        ix = vp_w / self.devicePixelRatio() - ir.width() - 16
        iy = vp_h / self.devicePixelRatio() - 20
        painter.fillRect(ix - 4, iy - ir.height() - 4, ir.width() + 8, ir.height() + 8,
                         QColor(0, 0, 0, 140))
        painter.drawText(ix, iy - 2, info_line)

        painter.end()

    def _draw_fallback(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(10, 10, 16))

        font = QFont("Consolas, monospace", 18)
        painter.setFont(font)
        painter.setPen(QColor(200, 200, 200, 200))
        msg = f"OpenGL not available.\nInstall PyOpenGL for the GPU stress test.\n\nGPU Temp: {self._gpu_temp:.0f}°C"
        painter.drawText(self.rect(), Qt.AlignCenter, msg)
        painter.end()

    def resizeGL(self, w, h):
        if HAS_OPENGL:
            GL.glViewport(0, 0, w * self.devicePixelRatio(), h * self.devicePixelRatio())

    def _perspective(self, fov, aspect, near, far):
        f = 1.0 / math.tan(math.radians(fov) / 2.0)
        d = near - far
        return [
            [f / aspect, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, (far + near) / d, 2 * far * near / d],
            [0, 0, -1, 0],
        ]

    def _look_at(self, eye, center, up):
        eye = np.array(eye, dtype=float)
        center = np.array(center, dtype=float)
        up = np.array(up, dtype=float)
        f = center - eye
        f /= np.linalg.norm(f)
        s = np.cross(f, up)
        s /= np.linalg.norm(s)
        u = np.cross(s, f)
        return [
            [s[0], s[1], s[2], -np.dot(s, eye)],
            [u[0], u[1], u[2], -np.dot(u, eye)],
            [-f[0], -f[1], -f[2], np.dot(f, eye)],
            [0, 0, 0, 1],
        ]

    def _rotate_y(self, angle):
        c, s = math.cos(angle), math.sin(angle)
        return [
            [c, 0, s, 0],
            [0, 1, 0, 0],
            [-s, 0, c, 0],
            [0, 0, 0, 1],
        ]

    def _rotate_x(self, angle):
        c, s = math.cos(angle), math.sin(angle)
        return [
            [1, 0, 0, 0],
            [0, c, -s, 0],
            [0, s, c, 0],
            [0, 0, 0, 1],
        ]


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

        screen = QApplication.primaryScreen()
        geo = screen.geometry()
        self.resize(geo.width(), geo.height())
        self.move(geo.x(), geo.y())
        self.showFullScreen()

        self._gl.start()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self._gl.stop()
        self.closed.emit()
        super().closeEvent(event)

    @property
    def fps(self):
        return self._gl.fps
