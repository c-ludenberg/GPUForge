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
    "extreme": UndervoltPreset(
        name="Extreme",
        description="Aggressive OC with higher power limit",
        power_limit_watts=350,
        core_clock_offset=150,
        mem_clock_offset=400,
    ),
    "overdrive": UndervoltPreset(
        name="OVERDRIVE",
        description="Maximum performance, use with extreme cooling",
        power_limit_watts=400,
        core_clock_offset=200,
        mem_clock_offset=600,
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


def get_profiles_dir() -> str:
    """Get the GPUForge profiles directory."""
    import platformdirs
    import os
    profiles = os.path.join(platformdirs.user_config_dir("GPUForge", ensure_exists=True), "profiles")
    os.makedirs(profiles, exist_ok=True)
    return profiles


def export_msi_afterburner_profile(preset: UndervoltPreset, voltage_curve: list[VoltagePoint] = None, save_to_profiles: bool = True) -> str:
    """Export preset as MSI Afterburner XML profile."""
    import xml.etree.ElementTree as ET

    root = ET.Element("MBProfile")
    root.set("version", "1.0")

    # Core clock offset
    core = ET.SubElement(root, "Card")
    core.set("type", "0")
    ET.SubElement(core, "str").text = "Core Clock"
    ET.SubElement(core, "val").text = str(preset.core_clock_offset)
    ET.SubElement(core, "sys").text = "0"

    # Memory clock offset
    mem = ET.SubElement(root, "Card")
    mem.set("type", "1")
    ET.SubElement(mem, "str").text = "Memory Clock"
    ET.SubElement(mem, "val").text = str(preset.mem_clock_offset)
    ET.SubElement(mem, "sys").text = "0"

    # Power limit (if set)
    if preset.power_limit_watts:
        power = ET.SubElement(root, "Card")
        power.set("type", "2")
        ET.SubElement(power, "str").text = "Power Limit"
        ET.SubElement(power, "val").text = str(preset.power_limit_watts)
        ET.SubElement(power, "sys").text = "0"

    # Voltage curve points (if provided)
    if voltage_curve:
        for i, point in enumerate(voltage_curve):
            vc = ET.SubElement(root, "Card")
            vc.set("type", "3")
            ET.SubElement(vc, "str").text = f"Voltage{i}"
            ET.SubElement(vc, "val").text = str(point.voltage_mv)
            ET.SubElement(vc, "sys").text = "0"

    xml_content = ET.tostring(root, encoding="unicode")

    # Auto-save to profiles folder
    if save_to_profiles:
        import os
        profiles_dir = get_profiles_dir()
        filename = os.path.join(profiles_dir, f"GPUForge_{preset.name.replace(' ', '_')}.xml")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(xml_content)
        except Exception:
            pass  # Silently fail if can't write

    return xml_content


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
