# GPUForge

> 🇵🇱 [Polski README](README.md)

Cross-platform GPU undervolt and overclocking tool.  
Built to beat NV-UV.

---

## Features

- Real-time GPU monitoring (temps, clocks, voltage, power, fans, utilization)
- Voltage-frequency curve editor
- One-click undervolt presets (Eco, Balanced, Performance, Max)
- Stress testing with crash detection
- Automatic game detection with preset switching
- Cross-platform (Windows + Linux)
- Beautiful dark theme

## Requirements

- OS: Windows 10/11 or Linux
- GPU: NVIDIA RTX 30/40/50 (via NVML) or AMD RDNA/RDNA2/RDNA3 (Linux)
- Python 3.11+

## Quick Start

```bash
pip install -r requirements.txt
python -m gpuforge.main
```

Or directly:

```bash
python src/gpuforge/main.py
```

## Building Standalone

```bash
pip install pyinstaller
pyinstaller gpuforge.spec
```

The executable will be in `dist/`.

## License

GPL-3.0
