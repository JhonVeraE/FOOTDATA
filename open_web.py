"""Open the local website, starting a loopback-only server when necessary."""
import argparse
import http.server
from functools import partial
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent

def is_our_site(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/assets/brand.svg',timeout=1) as response:
            return b'#d7f69c' in response.read(10000)
    except Exception:return False

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--serve',type=int);args=parser.parse_args()
    if args.serve:
        handler=partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT/'web'))
        http.server.ThreadingHTTPServer(('127.0.0.1',args.serve),handler).serve_forever()
        return
    port=8766
    while port<8786:
        if is_our_site(port):break
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',port));free=True
            except OSError:free=False
        if free:
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
            for _ in range(40):
                if is_our_site(port):break
                time.sleep(.1)
            if not is_our_site(port):raise RuntimeError('No se pudo iniciar el servidor de la web')
            break
        port+=1
    else:raise RuntimeError('No hay un puerto local disponible entre 8766 y 8785')
    webbrowser.open(f'http://127.0.0.1:{port}/#/')

if __name__=='__main__':main()
