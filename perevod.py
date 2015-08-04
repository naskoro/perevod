import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
from collections import namedtuple
from threading import Thread

from gi.repository import Gtk, Gdk, GObject

GObject.threads_init()

OK = 'OK'
RELOAD = 100
DEFAULT_CONFIG = """
lang = 'ru'
win_size = "830, 400"
win_move = "535, 365"
cmd = '''
    chromium --app='
        data:text/html,
        <html><body>
        <script>
            window.resizeTo({conf.win_size});
            window.moveTo({conf.win_move});
            window.location={url};
        </script>
        </body></html>'
'''
""".strip()


class Gui:
    def __init__(self, conf):
        if os.path.exists(conf.socket):
            if send_action(conf.socket, 'ping') == OK:
                print('Another `perevod` instance already run.')
                raise SystemExit(1)
            else:
                os.remove(conf.socket)

        # -- Menu
        start = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_MEDIA_PLAY, None)
        start.set_label('Translate')
        start.connect('activate', lambda w: self.pub_fetch())

        separator = Gtk.SeparatorMenuItem()

        quit = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_QUIT, None)
        quit.connect('activate', lambda w: self.pub_quit())

        menu = Gtk.Menu()
        for i in [start, separator, quit]:
            menu.append(i)

        menu.show_all()

        # -- Tray
        tray = Gtk.StatusIcon()
        tray.set_from_stock(Gtk.STOCK_SELECT_FONT)
        tray.connect('activate', lambda w: self.pub_fetch())
        tray.connect('popup-menu', lambda icon, button, time: (
            menu.popup(None, None, icon.position_menu, icon, button, time)
        ))

        # -- Window
        view = Gtk.Label(wrap=True, selectable=True)

        ok = Gtk.Button(label='Ok')
        ok.connect('clicked', lambda w: hide())
        ok.set_tooltip_text('Press "Enter" or "Esc"')
        link = Gtk.LinkButton('http://translate.google.com/')
        link.set_label('Open in browser')
        link.connect('clicked', lambda b: hide())
        bbox = Gtk.ButtonBox(spacing=6)
        bbox.set_halign(Gtk.Align.CENTER)
        bbox.pack_start(link, True, True, 0)
        bbox.pack_start(ok, True, True, 0)

        box = Gtk.VBox(spacing=0)
        box.pack_start(view, True, True, 5)
        box.pack_start(bbox, True, True, 5)

        win = Gtk.Window(
            title='Translate selection',
            skip_taskbar_hint=True, skip_pager_hint=True,
            type_hint=Gdk.WindowTypeHint.DIALOG,
            has_resize_grip=False
        )
        win.set_keep_above(True)
        win.connect('key-press-event', lambda w, e: (
            e.keyval in (Gdk.KEY_Return, Gdk.KEY_Escape) and hide()
        ))
        win.add(box)

        def hide():
            win.hide()

        # -- Bind to object
        self.conf = conf
        self.reload = False
        self.hide = hide

        # -- Start GTK loop
        server = Thread(target=self.serve, args=(conf.socket,))
        server.daemon = True
        server.start()

        signal.signal(signal.SIGINT, lambda s, f: self.pub_quit())
        try:
            Gtk.main()
        finally:
            if self.reload:
                print('Perevod reloading...')
                raise SystemExit(RELOAD)
            else:
                print('Perevod closed.')

    def serve(self, address):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(address)
        s.listen(1)

        while True:
            conn, addr = s.accept()
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                action = data.decode()
                action = getattr(self, 'pub_' + action)
                GObject.idle_add(action)
                conn.send(OK.encode())
        conn.close()

    def pub_quit(self):
        Gtk.main_quit()

    def pub_reload(self):
        self.reload = True
        self.pub_quit()

    def pub_fetch(self):
        clip = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        text = clip.wait_for_text().strip()
        if not (text and text.strip()):
            cmd = 'notify-send "Please select the text first"'
            subprocess.call(cmd, shell=True)
            return

        url = 'http://translate.google.com/#auto/ru/%s' % text
        url = json.dumps(url)
        cmd = self.conf.cmd.format(url=url, conf=self.conf)
        subprocess.call(cmd, shell=True)

    def pub_hide(self):
        self.hide()

    def pub_ping(self):
        pass


def send_action(address, action):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(address)
    except socket.error:
        return 'Error. No answer'
    s.send(action.encode())
    data = s.recv(1024)
    s.close()
    if data:
        return data.decode()
    return 'Error. Empty answer'


def get_actions():
    return [m[4:] for m in dir(Gui) if m.startswith('pub_')]


def get_config():
    conf_dirs = [
        os.path.join(os.path.dirname(__file__), 'var'),
        os.path.join(os.path.expanduser('~'), '.config', 'perevod')
    ]
    conf_dir = [p for p in conf_dirs if os.path.exists(p)]
    if conf_dir:
        conf_dir = conf_dir[0]
    else:
        conf_dir = conf_dirs[-1]
        os.mkdir(conf_dir)

    conf_path = os.path.join(conf_dir, 'config.py')
    conf = {}
    exec(DEFAULT_CONFIG, None, conf)
    if os.path.exists(conf_path):
        with open(conf_path, 'rb') as f:
            source = f.read()
        exec(source, None, conf)

    sid = '='.join([conf_dir, os.environ.get('XDG_SESSION_ID')])
    sid = hashlib.md5(sid.encode()).hexdigest()
    conf['socket'] = '/tmp/perevod-%s' % sid
    return namedtuple('Conf', conf.keys())(**conf)


def process_args(args):
    conf = get_config()
    parser = argparse.ArgumentParser()
    cmds = parser.add_subparsers(title='commands')

    def cmd(name, **kw):
        p = cmds.add_parser(name, **kw)
        p.set_defaults(cmd=name)
        p.arg = lambda *a, **kw: p.add_argument(*a, **kw) and p
        p.exe = lambda f: p.set_defaults(exe=f) and p
        return p

    cmd('call', help='call a specific action')\
        .arg('name', choices=get_actions(), help='select action')\
        .exe(lambda a: print(send_action(conf.socket, a.name)))

    cmd('conf', help='print default config')\
        .exe(lambda a: print(DEFAULT_CONFIG))

    args = parser.parse_args(args)
    if not hasattr(args, 'cmd'):
        Gui(conf)

    elif hasattr(args, 'exe'):
        args.exe(args)

    else:
        raise ValueError('Wrong subcommand')


def perevod(args=None):
    if args is None:
        args = sys.argv[1:]

    try:
        process_args(args)
    except KeyboardInterrupt:
        raise SystemExit()


if __name__ == '__main__':
    perevod()
