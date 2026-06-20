import logging
import os
import re
import glob
import sys
from typing import Optional

from gpuforge.backend.gpu_base import (
    GPUBackend,
    GPUError,
    GPUInfo,
    GPUSensors,
    UndervoltPreset,
    VoltagePoint,
)

log = logging.getLogger(__name__)

_HWMON_PATH = "/sys/class/drm/card*/device/hwmon/hwmon*/"
_DRM_PATH = "/sys/class/drm/card*/"


def _read_sysfs(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except (OSError, FileNotFoundError):
        return None


def _find_hwmon_dir(card_path: str) -> Optional[str]:
    hwmon_glob = os.path.join(card_path, "device", "hwmon", "hwmon*")
    dirs = sorted(glob.glob(hwmon_glob))
    return dirs[0] if dirs else None


class AMDBackend(GPUBackend):
    def __init__(self):
        self._cards: list[str] = []
        self._initialized = False

    def initialize(self) -> bool:
        if sys.platform != "linux":
            return False
        cards = sorted(glob.glob("/sys/class/drm/card*/"))
        self._cards = [c for c in cards if os.path.isdir(os.path.join(c, "device"))]
        self._initialized = len(self._cards) > 0
        return self._initialized

    def get_gpu_count(self) -> int:
        return len(self._cards)

    def _card_path(self, index: int) -> str:
        if index >= len(self._cards):
            raise GPUError(f"GPU index {index} out of range")
        return self._cards[index]

    def get_gpu_info(self, index: int) -> GPUInfo:
        card = self._card_path(index)
        name = _read_sysfs(os.path.join(card, "device", "product_name")) or "AMD GPU"
        vendor = _read_sysfs(os.path.join(card, "device", "vendor"))
        if vendor == "0x1002":
            name = f"AMD {name}"
        return GPUInfo(
            name=name,
            driver_version=_read_sysfs(os.path.join(card, "device", "driver", "module", "version")) or "",
            vbios_version="",
            pci_bus=os.path.basename(os.path.realpath(os.path.join(card, "device"))),
            index=index,
        )

    def get_sensors(self, index: int) -> GPUSensors:
        card = self._card_path(index)
        s = GPUSensors()

        hwmon = _find_hwmon_dir(card)
        if hwmon:
            for sensor in glob.glob(os.path.join(hwmon, "temp*_input")):
                label_file = sensor.replace("_input", "_label")
                label = _read_sysfs(label_file) or ""
                val = _read_sysfs(sensor)
                if val and label == "edge":
                    s.temp_core = int(val) / 1000.0
                elif val and label == "junction":
                    s.temp_hotspot = int(val) / 1000.0
                elif val and label == "mem":
                    s.temp_mem = int(val) / 1000.0

            fan_input = os.path.join(hwmon, "fan1_input")
            fan_val = _read_sysfs(fan_input)
            if fan_val:
                s.fan_rpm = int(fan_val)

            fan_pwm = os.path.join(hwmon, "pwm1")
            pwm_max = _read_sysfs(os.path.join(hwmon, "pwm1_max"))
            pwm_val = _read_sysfs(fan_pwm)
            if pwm_val and pwm_max:
                s.fan_speed_pct = (int(pwm_val) / int(pwm_max)) * 100.0

            power_input = os.path.join(hwmon, "power1_input")
            power_val = _read_sysfs(power_input)
            if power_val:
                s.power_watts = int(power_val) / 1000000.0

            power_cap = os.path.join(hwmon, "power1_cap")
            cap_val = _read_sysfs(power_cap)
            if cap_val:
                s.power_max_watts = int(cap_val) / 1000000.0

        device_path = os.path.join(card, "device")

        gpu_busy = _read_sysfs(os.path.join(device_path, "gpu_busy_percent"))
        if gpu_busy:
            s.utilization_pct = float(gpu_busy)

        mem_busy = _read_sysfs(os.path.join(device_path, "mem_busy_percent"))

        for perf in ["freq", "current_freq"]:
            freq_path = os.path.join(device_path, f"pp_dpm_sclk")
            freq_val = _read_sysfs(freq_path)
            if freq_val:
                freqs = re.findall(r'(\d+)Mhz', freq_val)
                if freqs:
                    s.gpu_clock = int(freqs[-1])

        for perf in ["freq", "current_freq"]:
            freq_path = os.path.join(device_path, f"pp_dpm_mclk")
            freq_val = _read_sysfs(freq_path)
            if freq_val:
                freqs = re.findall(r'(\d+)Mhz', freq_val)
                if freqs:
                    s.mem_clock = int(freqs[-1])

        vram_total = _read_sysfs(os.path.join(device_path, "mem_info_vram_total"))
        vram_used = _read_sysfs(os.path.join(device_path, "mem_info_vram_used"))
        if vram_total:
            s.mem_total_mb = int(vram_total) // (1024 * 1024)
        if vram_used:
            s.mem_used_mb = int(vram_used) // (1024 * 1024)

        volt_path = os.path.join(device_path, "pp_od_clk_voltage")
        volt_data = _read_sysfs(volt_path)
        if volt_data:
            voltages = re.findall(r'(\d+)\s+mv\s+(\d+)\s+Mhz', volt_data)
            if voltages:
                _, mhz = voltages[-1]
                volt_numbers = re.findall(r'(\d+)\s+mv', volt_data)
                if volt_numbers:
                    s.voltage = float(volt_numbers[-1])

        return s

    def get_voltage_curve(self, index: int) -> list[VoltagePoint]:
        card = self._card_path(index)
        device_path = os.path.join(card, "device")
        volt_path = os.path.join(device_path, "pp_od_clk_voltage")
        data = _read_sysfs(volt_path)
        if not data:
            return []
        points = []
        for line in data.split("\n"):
            m = re.match(r"(\d+)\s+mv\s+(\d+)\s+Mhz", line)
            if m:
                points.append(VoltagePoint(voltage_mv=int(m.group(1)), clock_mhz=int(m.group(2))))
        return points

    def apply_voltage_curve(self, index: int, points: list[VoltagePoint]) -> None:
        if sys.platform != "linux":
            raise GPUError("AMD voltage control only supported on Linux")
        card = self._card_path(index)
        device_path = os.path.join(card, "device")
        volt_path = os.path.join(device_path, "pp_od_clk_voltage")
        for point in points:
            cmd = f"{point.voltage_mv} {point.clock_mhz}"
            try:
                with open(volt_path, "w") as f:
                    f.write(cmd)
            except OSError as e:
                raise GPUError(f"Failed to set voltage point: {e}") from e

    def set_power_limit(self, index: int, watts: int) -> None:
        if sys.platform != "linux":
            raise GPUError("AMD power limit control only supported on Linux")
        card = self._card_path(index)
        hwmon = _find_hwmon_dir(card)
        if not hwmon:
            raise GPUError("No hwmon found for power limit")
        power_cap = os.path.join(hwmon, "power1_cap")
        try:
            with open(power_cap, "w") as f:
                f.write(str(watts * 1000000))
        except OSError as e:
            raise GPUError(f"Failed to set power cap: {e}") from e

    def set_clock_offsets(self, index: int, core_offset: int, mem_offset: int) -> None:
        pass

    def reset_to_defaults(self, index: int) -> None:
        if sys.platform != "linux":
            return
        card = self._card_path(index)
        device_path = os.path.join(card, "device")
        volt_path = os.path.join(device_path, "pp_od_clk_voltage")
        try:
            with open(volt_path, "w") as f:
                f.write("r")
        except OSError:
            pass

    def apply_preset(self, index: int, preset: UndervoltPreset) -> None:
        if preset.core_clock_offset != 0 or preset.mem_clock_offset != 0:
            self.set_clock_offsets(index, preset.core_clock_offset, preset.mem_clock_offset)
        if preset.power_limit_watts is not None:
            self.set_power_limit(index, preset.power_limit_watts)

    @staticmethod
    def is_available() -> bool:
        if sys.platform != "linux":
            return False
        cards = sorted(glob.glob("/sys/class/drm/card*/"))
        for card in cards:
            vendor = _read_sysfs(os.path.join(card, "device", "vendor"))
            if vendor == "0x1002":
                return True
        return False

