# Yeelight System Tray Controller

A lightweight Windows system tray app to control Yeelight smart bulbs.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- 💡 **System tray icon** - Lives quietly in your taskbar
- 🔄 **Quick toggle** - Double-click to toggle light on/off
- 🎚️ **Brightness control** - 10%, 25%, 50%, 75%, 100%
- 🌡️ **Color temperature** - Warm (2700K) to Daylight (6500K)
- ⚡ **Fast & lightweight** - No heavy dependencies

## Requirements

- Windows 10/11
- Python 3.8+
- Yeelight bulb with LAN Control enabled

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/user/yeelight-tray.git
   cd yeelight-tray
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure your bulb IP:**
   ```bash
   copy config.ini.example config.ini
   ```
   Edit `config.ini` and set your Yeelight bulb's IP address.

4. **Generate the icon:**
   ```bash
   python generate_icon.py
   ```

5. **Run:**
   ```bash
   pythonw yeelight_tray.pyw
   ```

## Finding Your Bulb's IP

1. Open the Yeelight app
2. Tap on your bulb → Settings (gear icon)
3. Look for "Device Info" → IP Address

**Or** check your router's connected devices list.

## Enabling LAN Control

LAN Control must be enabled on your Yeelight bulb:

1. Open Yeelight app
2. Tap your bulb → Settings (gear icon)
3. Enable **LAN Control**

## Usage

| Action | Result |
|--------|--------|
| **Double-click** tray icon | Toggle light on/off |
| **Right-click** tray icon | Open menu with all options |

## Auto-start with Windows

1. Press `Win + R`, type `shell:startup`, press Enter
2. Create a shortcut to `yeelight_tray.pyw` in that folder

## License

MIT License - feel free to use and modify.

## Contributing

Pull requests welcome! Please keep it simple and focused.

