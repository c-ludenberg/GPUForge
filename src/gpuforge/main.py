#!/usr/bin/env python3
import sys
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("gpuforge")


def detect_backends():
    from gpuforge.backend.nvidia_backend import NVIDIABackend
    from gpuforge.backend.amd_backend import AMDBackend

    backends = []

    if NVIDIABackend.is_available():
        nb = NVIDIABackend()
        if nb.initialize():
            backends.append(("NVIDIA", nb))
            log.info("NVIDIA backend initialized")

    if AMDBackend.is_available():
        ab = AMDBackend()
        if ab.initialize():
            backends.append(("AMD", ab))
            log.info("AMD backend initialized")

    return backends


AVAILABLE_LANGUAGES = {
    "pl": "Polski",
    "en": "English",
}

DEFAULT_LANGUAGE = "pl"

def setup_i18n(lang_code: str = None):
    import gettext
    import locale
    import json
    import platformdirs

    locale_dir = os.path.join(os.path.dirname(__file__), "locale")

    if lang_code is None:
        config_dir = platformdirs.user_config_dir("GPUForge", ensure_exists=True)
        config_path = os.path.join(config_dir, "settings.json")
        try:
            with open(config_path) as f:
                settings = json.load(f)
                lang_code = settings.get("language")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            lang_code = None

    if lang_code is None:
        try:
            locale.setlocale(locale.LC_ALL, "")
            sys_lang, _ = locale.getlocale()
            if sys_lang:
                lang_code = sys_lang[:2]
            else:
                lang_code = DEFAULT_LANGUAGE
        except locale.Error:
            lang_code = DEFAULT_LANGUAGE

    if lang_code not in AVAILABLE_LANGUAGES:
        lang_code = DEFAULT_LANGUAGE

    try:
        trans = gettext.translation("gpuforge", locale_dir, [lang_code], fallback=True)
        trans.install()
    except Exception:
        gettext.install("gpuforge", locale_dir, fallback=True)

    return lang_code


def save_language(lang_code: str):
    import json
    import platformdirs
    config_dir = platformdirs.user_config_dir("GPUForge", ensure_exists=True)
    config_path = os.path.join(config_dir, "settings.json")
    try:
        with open(config_path) as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}
    settings["language"] = lang_code
    with open(config_path, "w") as f:
        json.dump(settings, f)


def main():
    current_lang = setup_i18n()

    from PySide6.QtWidgets import QApplication
    from gpuforge.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("GPUForge")
    app.setOrganizationName("AntergosNeXT")

    backends = detect_backends()

    if not backends:
        log.warning("No compatible GPU backends found — launching demo mode")
        from gpuforge.backend.gpu_base import GPUBackend, GPUInfo, GPUSensors
        demo_name = _("No GPU Detected (Demo)")
        class DemoBackend(GPUBackend):
            def initialize(self): return True
            def get_gpu_count(self): return 1
            def get_gpu_info(self, i): return GPUInfo(name=demo_name, index=i)
            def get_sensors(self, i): return GPUSensors(temp_core=45.0, gpu_clock=0, power_watts=0, fan_speed_pct=0, utilization_pct=0)
            def get_voltage_curve(self, i): return []
            def apply_voltage_curve(self, i, p): pass
            def set_power_limit(self, i, w): pass
            def set_clock_offsets(self, i, c, m): pass
            def reset_to_defaults(self, i): pass
            def apply_preset(self, i, p): pass
        backend = DemoBackend()
    else:
        backend = backends[0][1]
        log.info("Using %s backend", backends[0][0])

    window = MainWindow(backend, current_lang=current_lang, available_languages=AVAILABLE_LANGUAGES, on_language_change=save_language)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
