from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GPUSensors:
    temp_core: float = 0.0
    temp_mem: float = 0.0
    temp_hotspot: float = 0.0
    gpu_clock: int = 0
    mem_clock: int = 0
    voltage: float = 0.0
    power_watts: float = 0.0
    power_max_watts: float = 0.0
    fan_speed_pct: float = 0.0
    fan_rpm: int = 0
    utilization_pct: float = 0.0
    mem_used_mb: int = 0
    mem_total_mb: int = 0


@dataclass
class GPUInfo:
    name: str = ""
    driver_version: str = ""
    vbios_version: str = ""
    pci_bus: str = ""
    index: int = 0


@dataclass
class VoltagePoint:
    voltage_mv: int
    clock_mhz: int


@dataclass
class UndervoltPreset:
    name: str = ""
    description: str = ""
    voltage_points: list[VoltagePoint] = field(default_factory=list)
    power_limit_watts: Optional[int] = None
    core_clock_offset: int = 0
    mem_clock_offset: int = 0


PRESETS_LIBRARY: dict[str, list[UndervoltPreset]] = {
    "eco": UndervoltPreset(
        name="Eco",
        description="Maximum efficiency, lower temps and power draw",
        power_limit_watts=None,
        core_clock_offset=-200,
        mem_clock_offset=-100,
    ),
    "balanced": UndervoltPreset(
        name="Balanced",
        description="Good performance with reduced power and heat",
        power_limit_watts=None,
        core_clock_offset=-100,
        mem_clock_offset=0,
    ),
    "performance": UndervoltPreset(
        name="Performance",
        description="Optimized voltage for sustained high clocks",
        power_limit_watts=None,
        core_clock_offset=0,
        mem_clock_offset=200,
    ),
    "max": UndervoltPreset(
        name="Max",
        description="Maximum overclock with undervolt for peak performance",
        power_limit_watts=None,
        core_clock_offset=100,
        mem_clock_offset=500,
    ),
}


class GPUError(Exception):
    pass


class GPUBackend(ABC):
    @abstractmethod
    def initialize(self) -> bool:
        ...

    @abstractmethod
    def get_gpu_count(self) -> int:
        ...

    @abstractmethod
    def get_gpu_info(self, index: int) -> GPUInfo:
        ...

    @abstractmethod
    def get_sensors(self, index: int) -> GPUSensors:
        ...

    @abstractmethod
    def get_voltage_curve(self, index: int) -> list[VoltagePoint]:
        ...

    @abstractmethod
    def apply_voltage_curve(self, index: int, points: list[VoltagePoint]) -> None:
        ...

    @abstractmethod
    def set_power_limit(self, index: int, watts: int) -> None:
        ...

    @abstractmethod
    def set_clock_offsets(self, index: int, core_offset: int, mem_offset: int) -> None:
        ...

    @abstractmethod
    def reset_to_defaults(self, index: int) -> None:
        ...

    @abstractmethod
    def apply_preset(self, index: int, preset: UndervoltPreset) -> None:
        ...
