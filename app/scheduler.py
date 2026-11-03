"""In-process Windows tray and sound/browser reminders with persisted suppression and DND."""
from __future__ import annotations
from datetime import datetime
import logging
import os
import threading
import webbrowser
from typing import Any
from . import db

ICON: Any = None

def eligible(config: dict[str, Any], current: datetime) -> bool:
    day, clock = current.date().isoformat(), current.strftime('%H:%M')
    state = db.get('reminder',day,{})
    if not config.get('enabled',False) or state.get('suppressed') or state.get('delivered') or config.get('away_until','')>=day:
        return False
    start, end = config.get('quiet_start','23:00'), config.get('quiet_end','08:00')
    quiet = start<=clock<end if start<end else clock>=start or clock<end if start!=end else False
    return not quiet and clock>=config.get('time','20:00')

def notify() -> list[str]:
    channels = []
    if ICON:
        try:
            ICON.notify('今天：读15分钟、写60分钟、闭卷15分钟。','地基 · 今天的三件事')
            channels.append('tray')
        except Exception:
            logging.exception('tray notification failed')
    try:
        import winsound
        winsound.Beep(880,1000)
        channels.append('sound')
    except (ImportError,RuntimeError):
        logging.exception('sound unavailable')
    if webbrowser.open('http://127.0.0.1:9890'):
        channels.append('browser')
    return channels

def tick(current: datetime | None = None) -> list[str]:
    current = current or datetime.now()
    if not eligible(db.get('setting','reminder',{}),current):
        return []
    channels = notify()
    if channels:
        db.put('reminder',current.date().isoformat(),{'delivered':True,'channels':channels,'at':current.isoformat()})
    return channels

def start(tray: bool = True) -> None:
    def loop() -> None:
        while True:
            try:
                tick()
                db.backup()
            except Exception:
                logging.exception('scheduler tick failed')
            threading.Event().wait(15)
    if tray:
        try:
            import pystray
            from PIL import Image, ImageDraw
            icon_class = pystray.Icon
            if os.name == 'nt':
                from pystray._util import win32
                class UserTray(pystray.Icon):
                    # pystray's elevated-message opt-in raises WinError 5 on some
                    # standard-user desktops. Ordinary tray messages need no opt-in.
                    def _create_window(self, atom: Any) -> Any:
                        return win32.CreateWindowEx(0,atom,None,win32.WS_POPUP,0,0,0,0,0,None,win32.GetModuleHandle(None),None)
                icon_class = UserTray
            image = Image.new('RGB',(64,64),'#151c22')
            draw = ImageDraw.Draw(image)
            draw.rectangle((13,35,51,49),fill='#b9da8c')
            draw.rectangle((23,18,41,32),fill='#b9da8c')
            def suppress(*_: Any) -> None:
                db.put('reminder',datetime.now().date().isoformat(),{'suppressed':True,'at':datetime.now().isoformat()})
            global ICON
            ICON = icon_class('groundwork',image,'地基 groundwork',pystray.Menu(
                pystray.MenuItem('打开今天',lambda *_: webbrowser.open('http://127.0.0.1:9890')),
                pystray.MenuItem('开始练习',lambda *_: webbrowser.open('http://127.0.0.1:9890/#practice')),
                pystray.MenuItem('今天不再提醒',suppress),
                pystray.MenuItem('退出',lambda *_: os._exit(0))))
            ICON.run_detached()
        except Exception:
            logging.exception('tray unavailable; sound and browser remain available')
    threading.Thread(target=loop,name='groundwork-reminder',daemon=True).start()
