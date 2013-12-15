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


def perevod():
    if os.path.exists(SOCK):
        if send_action('ping') == 'pong':
            print('Another `perevod` instance already run.')
            raise SystemExit(1)
        else:
            os.remove(SOCK)

    start = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_MEDIA_PLAY, None)
    start.set_label('Translate')
    start.connect('activate', lambda w: fetch())

    stop = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_MEDIA_STOP, None)
    stop.set_label('Hide translation window')
    stop.connect('activate', lambda w: hide())

    separator = Gtk.SeparatorMenuItem()

    quit = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_QUIT, None)
    quit.connect('activate', lambda w: main_quit())

    menu = Gtk.Menu()
    for i in [start, stop, separator, quit]:
        menu.append(i)

    menu.show_all()

    tray = Gtk.StatusIcon()
    tray.set_from_stock(Gtk.STOCK_SELECT_FONT)
    tray.connect('activate', lambda w: fetch())
    tray.connect('popup-menu', lambda icon, button, time: (
        menu.popup(None, None, icon.position_menu, icon, button, time)
    ))

    server = Thread(target=run_server)
    server.daemon = True
    server.start()

    signal.signal(signal.SIGINT, lambda s, f: main_quit())
    try:
        Gtk.main()
    finally:
        if hasattr(main_quit, 'reload'):
            print('Perevod reloading...')
            raise SystemExit(RELOAD)


def main_quit(reload=False):
    if reload:
        main_quit.reload = True

    os.remove(SOCK)
    Gtk.main_quit()


def fetch():
    clip = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
    text = clip.wait_for_text()
    if not (text and text.strip()):
        show('<b>WARN</b>: Please select the text first')
        return

        text = text.replace('\t', ' ').replace('\r', ' ')

    for lang in ['ru', 'en']:
        ok, result = call_google(text, to=lang)
        if ok and result['src_lang'] != lang:
            show(result['text'])
            return
        else:
            show('<b>ERROR</b>%s' % html.escape(str(result)))


def show(text):
    if not hasattr(show, 'win'):
        view = Gtk.Label('', wrap=True, selectable=True)

        win = Gtk.Window(
            title='Tider', decorated=True,
            skip_pager_hint=True, skip_taskbar_hint=True,
            type=Gtk.WindowType.POPUP
        )
        win.set_keep_above(True)
        win.add(view)
        win.move(950, 30)
        win.set_trans = lambda text: view.set_markup(text)

        show.win = win

    win = show.win
    win.set_trans(text)
    win.resize(400, 50)
    win.show_all()


def hide():
    if hasattr(show, 'win'):
        show.win.hide()


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


def run_server():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    s.listen(1)

    while True:
        conn, addr = s.accept()
        while True:
            data = conn.recv(1024)
            if not data:
                break
            action = data.decode()
            if action == 'ping':
                conn.send('pong'.encode())
            else:
                action = run_server.actions.get(data.decode())
                GObject.idle_add(action)
                conn.send('ok'.encode())
    conn.close()

run_server.actions = {
    'run': lambda: fetch(),
    'hide': lambda: hide(),
    'reload': lambda: main_quit(reload=True),
    'quit': lambda: main_quit(),
    'ping': None
}


def send_action(action):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(SOCK)
    except socket.error:
        return None
    s.send(action.encode())
    data = s.recv(1024)
    s.close()
    if data:
        return data.decode()
    return True


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
        .arg('name', choices=run_server.actions.keys(), help='choice action')\
        .exe(lambda a: print(send_action(a.name)))

    args = parser.parse_args(args)
    if hasattr(args, 'exe'):
        args.exe(args)
    else:
        raise ValueError('Wrong subcommand')


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    if not args:
        return perevod()

    try:
        process_args(args)
    except KeyboardInterrupt:
        raise SystemExit()


if __name__ == '__main__':
    main()
