"""
Yeelight System Tray Controller for Windows
Controls Yeelight smart bulbs from the Windows system tray.
"""
import socket
import threading
import configparser
import os
import sys

import win32api
import win32con
import win32gui

# Load config
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

def load_config():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    return {
        "ip": config.get("yeelight", "ip", fallback="192.168.1.100"),
        "port": config.getint("yeelight", "port", fallback=55443),
    }

cfg = load_config()
LIGHT_IP = cfg["ip"]
PORT = cfg["port"]


class YeelightController:
    """Controls a Yeelight bulb via TCP commands."""
    
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.cmd_id = 1
        self.lock = threading.Lock()

    def send(self, method, params="[]"):
        """Send a command to the Yeelight bulb."""
        with self.lock:
            try:
                cmd = f'{{"id":{self.cmd_id},"method":"{method}","params":{params}}}'
                self.cmd_id += 1
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                sock.connect((self.ip, self.port))
                sock.send((cmd + "\r\n").encode())
                sock.recv(1024)
                sock.close()
                return True
            except Exception:
                return False

    def on(self):
        self.send("set_power", '["on","smooth",500]')

    def off(self):
        self.send("set_power", '["off","smooth",500]')

    def toggle(self):
        self.send("toggle")

    def brightness(self, value):
        self.send("set_bright", f'[{value},"smooth",200]')

    def color_temp(self, value):
        self.send("set_ct_abx", f'[{value},"smooth",500]')


light = YeelightController(LIGHT_IP, PORT)


class SysTrayIcon:
    """Windows system tray icon handler."""
    
    QUIT = 'QUIT'
    FIRST_ID = 1023

    def __init__(self, icon, hover_text, menu_options, on_quit=None, default_menu_index=None):
        self.icon = icon
        self.hover_text = hover_text
        self.on_quit = on_quit

        menu_options = menu_options + (('Quit', None, self.QUIT),)
        self._next_action_id = self.FIRST_ID
        self.menu_actions_by_id = set()
        self.menu_options = self._add_ids_to_menu_options(list(menu_options))
        self.default_menu_index = default_menu_index

        self.window_class_name = "YeelightTray"

        wc = win32gui.WNDCLASS()
        wc.hInstance = win32gui.GetModuleHandle(None)
        wc.lpszClassName = self.window_class_name
        wc.lpfnWndProc = {
            win32con.WM_DESTROY: self.destroy,
            win32con.WM_COMMAND: self.command,
            win32con.WM_USER + 20: self.notify,
        }
        self.classAtom = win32gui.RegisterClass(wc)

        style = win32con.WS_OVERLAPPED | win32con.WS_SYSMENU
        self.hwnd = win32gui.CreateWindow(
            self.classAtom, self.window_class_name, style,
            0, 0, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT,
            0, 0, wc.hInstance, None
        )
        win32gui.UpdateWindow(self.hwnd)
        self._create_icon()

    def _add_ids_to_menu_options(self, menu_options):
        result = []
        for option in menu_options:
            text, icon, action = option
            if callable(action) or action == self.QUIT:
                self.menu_actions_by_id = set(list(self.menu_actions_by_id) + [(self._next_action_id, action)])
                result.append((text, icon, self._next_action_id))
                self._next_action_id += 1
            elif action is not None:
                result.append((text, icon, self._add_ids_to_menu_options(action)))
            else:
                result.append((text, icon, None))
        return result

    def _create_icon(self):
        try:
            icon = win32gui.LoadImage(
                0, self.icon, win32con.IMAGE_ICON,
                0, 0, win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
            )
        except Exception:
            icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        nid = (self.hwnd, 0, flags, win32con.WM_USER + 20, icon, self.hover_text)
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)

    def destroy(self, hwnd, msg, wparam, lparam):
        nid = (self.hwnd, 0)
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
        win32gui.PostQuitMessage(0)
        return None

    def notify(self, hwnd, msg, wparam, lparam):
        if lparam == win32con.WM_LBUTTONDBLCLK:
            threading.Thread(target=light.toggle, daemon=True).start()
        elif lparam == win32con.WM_RBUTTONUP:
            self.show_menu()
        return True

    def show_menu(self):
        menu = win32gui.CreatePopupMenu()
        self._create_menu(menu, self.menu_options)

        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, self.hwnd, None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

    def _create_menu(self, menu, options):
        for text, icon, action in options[::-1]:
            if action is None:
                win32gui.InsertMenu(menu, 0, win32con.MF_SEPARATOR, 0, '')
            elif isinstance(action, list):
                submenu = win32gui.CreatePopupMenu()
                self._create_menu(submenu, action)
                win32gui.InsertMenu(menu, 0, win32con.MF_BYPOSITION | win32con.MF_POPUP, submenu, text)
            else:
                win32gui.InsertMenu(menu, 0, win32con.MF_BYPOSITION, action, text)

    def command(self, hwnd, msg, wparam, lparam):
        action_id = win32api.LOWORD(wparam)
        action = None
        for aid, act in self.menu_actions_by_id:
            if aid == action_id:
                action = act
                break
        if action == self.QUIT:
            win32gui.DestroyWindow(self.hwnd)
        elif action:
            threading.Thread(target=action, daemon=True).start()
        return True


# Menu action functions
def on_toggle(): light.toggle()
def on_on(): light.on()
def on_off(): light.off()
def bright_100(): light.brightness(100)
def bright_75(): light.brightness(75)
def bright_50(): light.brightness(50)
def bright_25(): light.brightness(25)
def bright_10(): light.brightness(10)
def temp_warm(): light.color_temp(2700)
def temp_neutral(): light.color_temp(4000)
def temp_cool(): light.color_temp(5500)
def temp_day(): light.color_temp(6500)


menu_options = (
    ('Toggle', None, on_toggle),
    ('', None, None),
    ('Turn ON', None, on_on),
    ('Turn OFF', None, on_off),
    ('', None, None),
    ('Brightness', None, (
        ('100%', None, bright_100),
        ('75%', None, bright_75),
        ('50%', None, bright_50),
        ('25%', None, bright_25),
        ('10%', None, bright_10),
    )),
    ('Color Temp', None, (
        ('Warm (2700K)', None, temp_warm),
        ('Neutral (4000K)', None, temp_neutral),
        ('Cool (5500K)', None, temp_cool),
        ('Daylight (6500K)', None, temp_day),
    )),
)


if __name__ == '__main__':
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yeelight.ico")
    if not os.path.exists(icon_path):
        icon_path = None
    SysTrayIcon(icon_path, "Yeelight Control", menu_options)
    win32gui.PumpMessages()

