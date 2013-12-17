import argparse
import html
import json
import os
import signal
import socket
import sys
from importlib.machinery import SourceFileLoader
from threading import Thread
from urllib.error import URLError
from urllib.parse import urlencode, quote
from urllib.request import build_opener

from gi.repository import Gtk, Gdk, GObject

GObject.threads_init()

RELOAD = 100
DEFAULT_CONFIG = '''
def get(conf_dir):
    c = {}
    c['socket'] = '%s/default.sock' % (conf_dir)
    c['langs'] = ('ru', 'en')
    c['win_handler'] = win_handler
    return c


def win_handler(win):
    win.resize(400, 50)
    win.move(win.get_screen().get_width() - 410, 30)
'''.strip()


class Gui:
    def __init__(self, config):
        ### Menu
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

        ### Tray
        tray = Gtk.StatusIcon()
        tray.set_from_stock(Gtk.STOCK_SELECT_FONT)
        tray.connect('activate', lambda w: self.pub_fetch())
        tray.connect('popup-menu', lambda icon, button, time: (
            menu.popup(None, None, icon.position_menu, icon, button, time)
        ))

        ### Window
        view = Gtk.Label(wrap=True, selectable=True)

        ok = Gtk.Button(label='Ok')
        ok.connect('clicked', lambda w: hide())
        link = Gtk.LinkButton('http://translate.google.com/')
        link.set_label('Open in browser')
        bbox = Gtk.ButtonBox(spacing=6)
        bbox.set_halign(Gtk.Align.CENTER)
        bbox.pack_start(link, True, True, 0)
        bbox.pack_start(ok, True, True, 0)

        box = Gtk.VBox(spacing=0)
        box.pack_start(view, True, True, 5)
        box.pack_start(bbox, True, True, 5)
        box.connect('key-press-event', lambda w, e: (
            e.keyval == Gdk.KEY_Return and hide()
        ))

        win = Gtk.Window(
            title='Translate selection',
            skip_taskbar_hint=True, skip_pager_hint=True,
            type_hint=Gdk.WindowTypeHint.DIALOG,
            has_resize_grip=False
        )
        win.set_keep_above(True)
        win.add(box)

        def show(text, url=None):
            if url:
                link.set_uri(url)
            view.set_markup(text)
            config['win_handler'](win)
            view.set_size_request(win.get_size()[0], 1)
            win.show_all()

        def hide():
            win.hide()

        ### Bind to object
        self.config = config
        self.reload = False
        self.hide = hide
        self.show = show

        ### Start GTK loop
        server = Thread(target=self.serve, args=(config['socket'],))
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

    def serve(self, sockfile):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(sockfile)
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
                conn.send('ok'.encode())
        conn.close()

    def pub_quit(self):
        Gtk.main_quit()

    def pub_reload(self):
        self.reload = True
        self.pub_quit()

    def pub_fetch(self):
        clip = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        text = clip.wait_for_text()
        if not (text and text.strip()):
            self.show('<b>Warning</b>: Please select the text first')
            return

            text = text.replace('\t', ' ').replace('\r', ' ')

        self.show('<b>Loading...</b>')
        for lang in self.config['langs']:
            ok, result = call_google(text, to=lang)
            if ok and result['src_lang'] != lang:
                self.show(result['text'], url=result['url'])
                return
            else:
                self.show('<b>Error</b>%s' % html.escape(str(result)))

    def pub_hide(self):
        self.hide()

    def pub_ping(self):
        pass


def call_google(text, to):
    url = 'http://translate.google.ru/translate_a/t'
    params = {
        'client': 'x',
        'sl': 'auto',
        'tl': to,
        'io': 'utf8',
        'oe': 'utf8',
        'text': text
    }

    opener = build_opener()
    opener.addheaders = [('User-agent', 'Mozilla/5.0')]
    try:
        f = opener.open('%s?%s' % (url, urlencode(params)))
    except URLError as e:
        return False, e
    data = json.loads(f.read().decode())

    url_ = 'http://translate.google.com/#auto/%s/%s' % (to, quote(text))
    text_ = '\n'.join(r['trans'] for r in data['sentences'])
    return True, {'src_lang': data['src'], 'text': text_, 'url': url_}


def send_action(sockfile, action):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(sockfile)
    except socket.error:
        return None
    s.send(action.encode())
    data = s.recv(1024)
    s.close()
    if data:
        return data.decode()
    return True


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
    if not os.path.exists(conf_path):
        with open(conf_path, 'wb') as f:
            f.write(DEFAULT_CONFIG.encode())

    loader = SourceFileLoader('config', conf_path)
    config = loader.load_module('config')
    config = config.get(conf_dir)
    return config


def process_args(args):
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
        .exe(lambda a: print(send_action(sockfile, a.name)))

    cmd('config', help='print default config')\
        .exe(lambda a: print(DEFAULT_CONFIG))

    args = parser.parse_args(args)
    config = get_config()
    sockfile = config['socket']
    if not hasattr(args, 'cmd'):
        if os.path.exists(sockfile):
            if send_action(sockfile, 'ping') == 'ok':
                print('Another `perevod` instance already run.')
                raise SystemExit(1)
            else:
                os.remove(sockfile)

        Gui(config)

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
