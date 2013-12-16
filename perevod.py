import argparse
import html
import json
import os
import signal
import socket
import sys
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import build_opener
from threading import Thread

from gi.repository import Gtk, Gdk, GObject

GObject.threads_init()

SOCK = '/tmp/perevod.pid'
RELOAD = 100


class Gui:
    def __init__(self, sockfile):
        ### Menu
        start = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_MEDIA_PLAY, None)
        start.set_label('Translate')
        start.connect('activate', lambda w: self.pub_fetch())

        stop = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_MEDIA_STOP, None)
        stop.set_label('Hide translation window')
        stop.connect('activate', lambda w: self.pub_hide())

        separator = Gtk.SeparatorMenuItem()

        quit = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_QUIT, None)
        quit.connect('activate', lambda w: self.pub_quit())

        menu = Gtk.Menu()
        for i in [start, stop, separator, quit]:
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
        win = Gtk.Dialog(accept_focus=False)
        view = Gtk.Label(wrap=True, selectable=True)
        box = win.get_content_area()
        box.add(view)
        win.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK)

        def show(text):
            view.set_markup(text)
            view.set_size_request(400, 1)
            win.resize(400, 1)
            win.move(950, 30)
            win.show_all()
            response = win.run()
            if response == Gtk.ResponseType.OK:
                pass

            win.hide()

        def hide():
            win.hide()

        ### Bind to object
        self.hide = hide
        self.show = show
        self.reload = False

        ### Start GTK loop
        server = Thread(target=self.serve, args=(sockfile,))
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

        #self.show('<b>Loading...</b>')
        for lang in ['ru', 'en']:
            ok, result = call_google(text, to=lang)
            if ok and result['src_lang'] != lang:
                self.show(result['text'])
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
    text = '\n'.join(r['trans'] for r in data['sentences'])
    return True, {'src_lang': data['src'], 'text': text}


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

    args = parser.parse_args(args)
    sockfile = SOCK
    if not hasattr(args, 'name'):
        if os.path.exists(sockfile):
            if send_action(sockfile, 'ping') == 'ok':
                print('Another `perevod` instance already run.')
                raise SystemExit(1)
            else:
                os.remove(sockfile)

        Gui(sockfile)

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
