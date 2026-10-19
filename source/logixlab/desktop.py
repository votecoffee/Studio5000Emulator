"""Windows notification-area controls, using only the Python standard library."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import webbrowser

from . import __version__


class TrayIcon:
    """Own a hidden Win32 window and icon on a dedicated message-loop thread."""

    def __init__(self, url, on_quit, on_import=None):
        self.url = url
        self.on_quit = on_quit
        self.on_import = on_import
        self.available = False
        self.error = None
        self._ready = threading.Event()
        self._thread = None
        self._hwnd = None
        self._user = None
        self._stopping = threading.Event()

    def start(self):
        if sys.platform != 'win32':
            return False
        self._thread = threading.Thread(target=self._run, name='LogixLab tray', daemon=True)
        self._thread.start()
        if not self._ready.wait(5):
            self.error = 'The Windows tray did not start in time'
            self.stop()
        return self.available

    def stop(self):
        # Only the message-loop thread destroys its window and removes the icon.
        self._stopping.set()
        if self._hwnd and self._user:
            self._user.PostMessageW(self._hwnd, 0x0010, 0, 0)  # WM_CLOSE
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)

    def _run(self):
        try:
            self._windows_loop()
        except Exception as error:
            self.error = str(error)
        finally:
            self._ready.set()

    def _windows_loop(self):
        import ctypes as c
        from ctypes import wintypes as w

        result_type = c.c_ssize_t  # LRESULT is pointer-sized on 64-bit Windows.
        wndproc_type = c.WINFUNCTYPE(result_type, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

        class WindowClass(c.Structure):
            _fields_ = [('style', w.UINT), ('wndproc', wndproc_type), ('class_extra', c.c_int),
                        ('window_extra', c.c_int), ('instance', w.HINSTANCE), ('icon', w.HICON),
                        ('cursor', w.HANDLE), ('background', w.HBRUSH),
                        ('menu_name', w.LPCWSTR), ('class_name', w.LPCWSTR)]

        class Guid(c.Structure):
            _fields_ = [('data1', w.DWORD), ('data2', w.WORD), ('data3', w.WORD), ('data4', w.BYTE * 8)]

        class IconData(c.Structure):
            _fields_ = [('size', w.DWORD), ('window', w.HWND), ('id', w.UINT), ('flags', w.UINT),
                        ('message', w.UINT), ('icon', w.HICON), ('tip', w.WCHAR * 128),
                        ('state', w.DWORD), ('state_mask', w.DWORD), ('info', w.WCHAR * 256),
                        ('version', w.UINT), ('info_title', w.WCHAR * 64), ('info_flags', w.DWORD),
                        ('guid', Guid), ('balloon_icon', w.HICON)]

        def bind(dll, name, returns, *args):
            function = getattr(dll, name)
            function.restype, function.argtypes = returns, args
            return function

        user = c.WinDLL('user32', use_last_error=True)
        shell = c.WinDLL('shell32', use_last_error=True)
        kernel = c.WinDLL('kernel32', use_last_error=True)
        self._user = user
        bind(kernel, 'GetModuleHandleW', w.HMODULE, w.LPCWSTR)
        bind(user, 'RegisterClassW', w.ATOM, c.POINTER(WindowClass))
        bind(user, 'UnregisterClassW', w.BOOL, w.LPCWSTR, w.HINSTANCE)
        bind(user, 'CreateWindowExW', w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
             c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
        bind(user, 'DefWindowProcW', result_type, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        bind(user, 'DestroyWindow', w.BOOL, w.HWND)
        bind(user, 'PostMessageW', w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        bind(user, 'PostQuitMessage', None, c.c_int)
        bind(user, 'GetMessageW', c.c_int, c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
        bind(user, 'TranslateMessage', w.BOOL, c.POINTER(w.MSG))
        bind(user, 'DispatchMessageW', result_type, c.POINTER(w.MSG))
        bind(user, 'RegisterWindowMessageW', w.UINT, w.LPCWSTR)
        bind(user, 'LoadImageW', w.HANDLE, w.HINSTANCE, w.LPCWSTR, w.UINT, c.c_int, c.c_int, w.UINT)
        bind(user, 'GetSystemMetrics', c.c_int, c.c_int)
        bind(user, 'DestroyIcon', w.BOOL, w.HICON)
        bind(user, 'CreatePopupMenu', w.HMENU)
        bind(user, 'AppendMenuW', w.BOOL, w.HMENU, w.UINT, c.c_size_t, w.LPCWSTR)
        bind(user, 'SetMenuDefaultItem', w.BOOL, w.HMENU, w.UINT, w.UINT)
        bind(user, 'DestroyMenu', w.BOOL, w.HMENU)
        bind(user, 'GetCursorPos', w.BOOL, c.POINTER(w.POINT))
        bind(user, 'SetForegroundWindow', w.BOOL, w.HWND)
        bind(user, 'TrackPopupMenu', w.UINT, w.HMENU, w.UINT, c.c_int, c.c_int,
             c.c_int, w.HWND, c.c_void_p)
        bind(shell, 'Shell_NotifyIconW', w.BOOL, w.DWORD, c.POINTER(IconData))

        callback_message = 0x8001  # WM_APP + 1
        taskbar_created = user.RegisterWindowMessageW('TaskbarCreated')
        icon = IconData()
        menu = None
        instance = kernel.GetModuleHandleW(None)
        class_name = f'LogixLab.Tray.{os.getpid()}.{id(self)}'
        registered = False
        owned_icon = None

        def add_icon():
            icon.flags = 1 | 2 | 4 | 0x80  # MESSAGE, ICON, TIP, SHOWTIP
            self.available = bool(shell.Shell_NotifyIconW(0, c.byref(icon)))
            if self.available:
                icon.version = 4
                if not shell.Shell_NotifyIconW(4, c.byref(icon)):
                    raise OSError('Windows could not set the notification icon version')
            return self.available

        def open_app():
            # Browser launching must not block the window's message loop.
            threading.Thread(target=webbrowser.open, args=(self.url,), daemon=True).start()

        def popup(hwnd):
            nonlocal menu
            point = w.POINT()
            user.GetCursorPos(c.byref(point))
            menu = user.CreatePopupMenu()
            if not menu:
                raise c.WinError(c.get_last_error())
            try:
                user.AppendMenuW(menu, 2, 0, f'LogixLab {__version__}')  # disabled title
                user.AppendMenuW(menu, 2, 0, self.url)
                user.AppendMenuW(menu, 0x800, 0, None)  # separator
                user.AppendMenuW(menu, 0, 1, 'Open app')
                if self.on_import:
                    user.AppendMenuW(menu, 0, 3, 'Import ACD / L5X...')
                user.AppendMenuW(menu, 0, 2, 'Quit LogixLab')
                user.SetMenuDefaultItem(menu, 1, False)
                user.SetForegroundWindow(hwnd)
                command = user.TrackPopupMenu(menu, 0x100 | 2, point.x, point.y, 0, hwnd, None)
                if command == 1:
                    open_app()
                elif command == 2:
                    self.on_quit()
                elif command == 3 and self.on_import:
                    threading.Thread(target=self.on_import, daemon=True).start()
                user.PostMessageW(hwnd, 0, 0, 0)
            finally:
                user.DestroyMenu(menu)
                menu = None

        @wndproc_type
        def window_proc(hwnd, message, wp, lp):
            try:
                if message == taskbar_created and taskbar_created:
                    add_icon()  # Restore after Explorer restarts.
                    return 0
                if message == callback_message:
                    event = lp & 0xffff
                    if event in (0x400, 0x401):  # NIN_SELECT, NIN_KEYSELECT
                        open_app()
                    elif event == 0x7b:  # WM_CONTEXTMENU
                        popup(hwnd)
                    return 0
                if message == 0x10:
                    user.DestroyWindow(hwnd)
                    return 0
                if message == 2:  # WM_DESTROY
                    shell.Shell_NotifyIconW(2, c.byref(icon))
                    self.available = False
                    user.PostQuitMessage(0)
                    return 0
            except Exception as error:
                # Never allow an exception to cross a native callback boundary.
                self.error = str(error)
            return user.DefWindowProcW(hwnd, message, wp, lp)

        try:
            icon_path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'web/icons/plc-simulator.ico'
            owned_icon = user.LoadImageW(None, str(icon_path), 1,
                                        user.GetSystemMetrics(49), user.GetSystemMetrics(50), 0x10)
            if not owned_icon:
                raise c.WinError(c.get_last_error())
            wc = WindowClass()
            wc.wndproc, wc.instance, wc.class_name = window_proc, instance, class_name
            wc.icon = owned_icon
            if not user.RegisterClassW(c.byref(wc)):
                raise c.WinError(c.get_last_error())
            registered = True
            # A hidden top-level window receives the Explorer broadcast; a
            # message-only window would miss TaskbarCreated.
            self._hwnd = user.CreateWindowExW(0, class_name, f'LogixLab {__version__}',
                                              0, 0, 0, 0, 0, None, None, instance, None)
            if not self._hwnd:
                raise c.WinError(c.get_last_error())
            if self._stopping.is_set():
                return
            icon.size, icon.window, icon.id = c.sizeof(icon), self._hwnd, 1
            icon.message = callback_message
            icon.icon = owned_icon
            icon.tip = f'LogixLab {__version__}\n{self.url}'[:127]
            if not add_icon():
                raise OSError('Windows could not add the notification icon')
            self._ready.set()
            message = w.MSG()
            while True:
                status = user.GetMessageW(c.byref(message), None, 0, 0)
                if status == -1:
                    raise c.WinError(c.get_last_error())
                if status == 0:
                    break
                user.TranslateMessage(c.byref(message))
                user.DispatchMessageW(c.byref(message))
        except Exception as error:
            self.error = str(error)
        finally:
            if self._hwnd:
                shell.Shell_NotifyIconW(2, c.byref(icon))
                user.DestroyWindow(self._hwnd)
            self._hwnd = None
            self.available = False
            if registered:
                user.UnregisterClassW(class_name, instance)
            if owned_icon:
                user.DestroyIcon(owned_icon)
            self._ready.set()
