import logging
import subprocess
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


def _run_nvidia_smi(*args: str) -> str:
    try:
        result = subprocess.run(
            ["nvidia-smi", *args],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise GPUError(f"nvidia-smi error: {result.stderr.strip()}")
        return result.stdout.strip()
    except FileNotFoundError as e:
        raise GPUError("nvidia-smi not found") from e
    except subprocess.TimeoutExpired as e:
        raise GPUError("nvidia-smi timed out") from e


class NVIDIABackend(GPUBackend):
    def __init__(self):
        self._pynvml = None
        self._initialized = False

    def initialize(self) -> bool:
        try:
            import pynvml
            self._pynvml = pynvml
            self._pynvml.nvmlInit()
            self._initialized = True
            return True
        except Exception as e:
            log.warning("NVML init failed: %s", e)
            return False

    def get_gpu_count(self) -> int:
        return self._pynvml.nvmlDeviceGetCount()

    def _handle(self, index: int):
        return self._pynvml.nvmlDeviceGetHandleByIndex(index)

    def get_gpu_info(self, index: int) -> GPUInfo:
        handle = self._handle(index)
        name = self._pynvml.nvmlDeviceGetName(handle)
        try:
            driver = self._pynvml.nvmlSystemGetDriverVersion()
        except Exception:
            driver = ""
        try:
            vbios = self._pynvml.nvmlDeviceGetVbiosVersion(handle)
        except Exception:
            vbios = ""
        try:
            pci_info = self._pynvml.nvmlDeviceGetPciInfo(handle)
            bus = f"{pci_info.bus:08X}:{pci_info.device:02X}.{pci_info.function}"
        except Exception:
            bus = ""
        return GPUInfo(name=name, driver_version=driver, vbios_version=vbios, pci_bus=bus, index=index)

    def get_sensors(self, index: int) -> GPUSensors:
        handle = self._handle(index)
        s = GPUSensors()

        try:
            temp = self._pynvml.nvmlDeviceGetTemperature(handle, self._pynvml.NVML_TEMPERATURE_GPU)
            s.temp_core = float(temp)
        except Exception:
            pass

        try:
            mem_temp = self._pynvml.nvmlDeviceGetTemperature(handle, self._pynvml.NVML_TEMPERATURE_MEMORY)
            s.temp_mem = float(mem_temp)
        except Exception:
            pass

        try:
            util = self._pynvml.nvmlDeviceGetUtilizationRates(handle)
            s.utilization_pct = float(util.gpu)
        except Exception:
            pass

        try:
            clocks = self._pynvml.nvmlDeviceGetClockInfo(handle, self._pynvml.NVML_CLOCK_GRAPHICS)
            s.gpu_clock = int(clocks)
        except Exception:
            pass

        try:
            mem_clocks = self._pynvml.nvmlDeviceGetClockInfo(handle, self._pynvml.NVML_CLOCK_MEM)
            s.mem_clock = int(mem_clocks)
        except Exception:
            pass

        try:
            power = self._pynvml.nvmlDeviceGetPowerUsage(handle)
            s.power_watts = power / 1000.0
        except Exception:
            pass

        try:
            power_limit = self._pynvml.nvmlDeviceGetPowerManagementLimit(handle)
            s.power_max_watts = power_limit / 1000.0
        except Exception:
            pass

        try:
            fan = self._pynvml.nvmlDeviceGetFanSpeed(handle)
            s.fan_speed_pct = float(fan)
        except Exception:
            pass

        try:
            fan_rpm = self._pynvml.nvmlDeviceGetFanSpeedRPM(handle) if hasattr(self._pynvml, 'nvmlDeviceGetFanSpeedRPM') else 0
            s.fan_rpm = int(fan_rpm)
        except Exception:
            pass

        try:
            mem_info = self._pynvml.nvmlDeviceGetMemoryInfo(handle)
            s.mem_total_mb = mem_info.total // (1024 * 1024)
            s.mem_used_mb = (mem_info.total - mem_info.free) // (1024 * 1024)
        except Exception:
            pass

        return s

    def get_voltage_curve(self, index: int) -> list[VoltagePoint]:
        return []

    def apply_voltage_curve(self, index: int, points: list[VoltagePoint]) -> None:
        raise GPUError("Voltage curve control not implemented via NVML")

    def set_power_limit(self, index: int, watts: int) -> None:
        handle = self._handle(index)
        self._pynvml.nvmlDeviceSetPowerManagementLimit(handle, watts * 1000)

    def set_clock_offsets(self, index: int, core_offset: int, mem_offset: int) -> None:
        handle = self._handle(index)
        try:
            self._pynvml.nvmlDeviceSetGpuLockedClocks(handle, 0, 3000)
        except Exception:
            pass
        try:
            min_mem = 0
            max_mem = 20001
            self._pynvml.nvmlDeviceSetMemLockedClocks(handle, min_mem, max_mem)
        except Exception:
            pass

    def reset_to_defaults(self, index: int) -> None:
        handle = self._handle(index)
        try:
            self._pynvml.nvmlDeviceResetGpuLockedClocks(handle)
        except Exception:
            pass
        try:
            self._pynvml.nvmlDeviceResetMemLockedClocks(handle)
        except Exception:
            pass
        try:
            default_power = self._pynvml.nvmlDeviceGetPowerManagementDefaultLimit(handle)
            self._pynvml.nvmlDeviceSetPowerManagementLimit(handle, default_power)
        except Exception:
            pass

    def apply_preset(self, index: int, preset: UndervoltPreset) -> None:
        self.set_clock_offsets(index, preset.core_clock_offset, preset.mem_clock_offset)
        if preset.power_limit_watts is not None:
            self.set_power_limit(index, preset.power_limit_watts)

    @staticmethod
    def is_available() -> bool:
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
            return True
        except Exception:
            return False
