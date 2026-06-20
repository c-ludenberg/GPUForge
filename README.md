# GPUForge

> 🇬🇧 [English README](README.en.md)

Wieloplatformowe narzędzie do undervoltingu i overclockingu GPU.  
Zbudowane po to, by pokonać NV-UV.

---

## Cechy

- Monitorowanie GPU w czasie rzeczywistym (temperatura, taktowanie, napięcie, moc, wentylatory, wykorzystanie)
- Edytor krzywej napięcie-częstotliwość
- Profile undervoltu jednym kliknięciem (Eco, Balanced, Performance, Max)
- Test obciążenia z wykrywaniem crashy
- Automatyczne wykrywanie gier z przełączaniem profili
- Wieloplatformowość (Windows + Linux)
- Piękny ciemny motyw

## Wymagania

- System operacyjny: Windows 10/11 lub Linux
- GPU: NVIDIA RTX 30/40/50 (przez NVML) lub AMD RDNA/RDNA2/RDNA3 (Linux)
- Python 3.11+

## Szybki start

```bash
pip install -r requirements.txt
python -m gpuforge.main
```

Lub bezpośrednio:

```bash
python src/gpuforge/main.py
```

## Budowanie wersji przenośnej

```bash
pip install pyinstaller
pyinstaller gpuforge.spec
```

Gotowy plik wykonywalny znajdziesz w katalogu `dist/`.

## Struktura projektu

```
src/gpuforge/
├── main.py                   # Punkt wejścia + konfiguracja i18n
├── backend/                  # Silnik GPU
│   ├── gpu_base.py           # Abstrakcyjna klasa bazowa + profile
│   ├── nvidia_backend.py     # NVIDIA przez NVML
│   ├── amd_backend.py        # AMD przez sysfs
│   └── monitor.py            # Wątek odczytu sensorów
├── ui/                       # Interfejs graficzny
│   ├── main_window.py        # Główne okno + nawigacja
│   ├── monitor_widget.py     # Kafelki sensorów + wykresy
│   ├── curve_editor.py       # Edytor offsetów zegara
│   ├── presets.py            # Profile jednym kliknięciem
│   ├── stress_test.py        # Test obciążenia
│   └── game_detector.py      # Wykrywanie gier
├── locale/
│   ├── gpuforge.pot          # Szablon tłumaczeń
│   └── pl/LC_MESSAGES/       # Polskie tłumaczenie
└── resources/
    └── style.qss             # Motyw ciemny
```

## Licencja

GPL-3.0
