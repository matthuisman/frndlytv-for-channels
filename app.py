#!/usr/bin/python3
import os
import time
import argparse
import datetime as dt
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qsl
from xml.sax.saxutils import escape
import requests

from frndly import Frndly

PLAYLIST_URL = 'playlist.m3u8'
PLAYLIST_URL_LEGACY = 'playlist.m3u'
EPG_URL = 'epg.xml'
PLAY = 'play'
KEEP_ALIVE = 'keep_alive'
STATUS_URL = ''

class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self._params = {}
        super().__init__(*args, **kwargs)

    def _error(self, message):
        self.send_response(500)
        self.end_headers()
        self.wfile.write(f'Error: {message}'.encode('utf8'))
        raise

    def do_GET(self):
        routes = {
            PLAYLIST_URL: self._playlist,
            PLAYLIST_URL_LEGACY: self._playlist,
            EPG_URL: self._epg,
            PLAY: self._play,
            KEEP_ALIVE: self._keep_alive,
            STATUS_URL: self._status,
        }

        parsed = urlparse(self.path)
        func = parsed.path.split('/')[1]
        self._params = dict(parse_qsl(parsed.query, keep_blank_values=True))

        if func not in routes:
            self.send_response(404)
            self.end_headers()
            return

        try:
            routes[func]()
        except Exception as e:
            self._error(e)

    def _keep_alive(self):
        frndly.keep_alive()
        self.send_response(200)
        self.end_headers()

    def _play(self):
        slug = self.path.split('/')[-1].split('.')[0]
        url = frndly.play(slug)

        self.send_response(302)
        self.send_header('location', url)
        self.end_headers()

    def _playlist(self):
        channels = frndly.channels()
        live_map = frndly.live_map()

        host = self.headers.get('Host')
        self.send_response(200)
        self.end_headers()

        start_chno = int(self._params['start_chno']) if 'start_chno' in self._params else None
        include = [x.lower().strip() for x in self._params.get('include', '').split(',') if x.strip()]
        exclude = [x.lower().strip() for x in self._params.get('exclude', '').split(',') if x.strip()]
        gracenote = self._params.get('gracenote', '').lower().strip()

        epg_url = f"http://{host}/{EPG_URL}"
        if gracenote:
            epg_url += f'?gracenote={gracenote}'

        self.wfile.write(f'#EXTM3U x-tvg-url="{epg_url}"\n'.encode('utf8'))
        for row in channels:
            id = str(row['id'])
            channel_id = f'frndly-{id}'
            data = live_map.get(id) or {}
            slug = data.get('slug') or id
            url = f'http://{host}/{PLAY}/{slug}.m3u8'
            name = row['display']['title']
            logo = frndly.logo(row['display']['imageUrl'])
            gracenote_id = data.get('gracenote')

            if (include and channel_id.lower() not in include) or (exclude and channel_id.lower() in exclude):
                print(f"Skipping {channel_id} due to include / exclude")
                continue

            if (gracenote == 'include' and not gracenote_id) or (gracenote == 'exclude' and gracenote_id):
                print(f"Skipping {channel_id} due to gracenote")
                continue

            if gracenote_id:
                gracenote_id = ' tvc-guide-stationid="{}"'.format(gracenote_id)
            else:
                gracenote_id = ''
                print(f'No gracenote id found in epg map for: {id}')

            chno = ''
            if start_chno is not None:
                if start_chno > 0:
                    chno = f' tvg-chno="{start_chno}"'
                    start_chno += 1

            self.wfile.write(f'#EXTINF:-1 channel-id="{channel_id}" tvg-id="{channel_id}" tvg-logo="{logo}"{gracenote_id}{chno},{name}\n{url}\n'.encode('utf8'))

    def _epg(self):
        channels = frndly.channels()
        live_map = frndly.live_map()

        try: days = int(self._params.get('days', ''))
        except: days = 3
        gracenote = self._params.get('gracenote', '').lower().strip()

        if days > 7:
            days = 7

        if days < 1:
            days = 1

        self.send_response(200)
        self.end_headers()

        self.wfile.write(b'<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE tv SYSTEM "xmltv.dtd"><tv generator-info-name="www.matthuisman.nz">')
        ids = []
        for row in channels:
            id = str(row['id'])
            channel_id = f'frndly-{id}'
            data = live_map.get(id) or {}
            gracenote_id = data.get('gracenote')
            name = escape(row['display']['title'])

            if (gracenote == 'include' and not gracenote_id) or (gracenote == 'exclude' and gracenote_id):
                print(f"Skipping {channel_id} due to gracenote")
                continue

            ids.append(id)
            self.wfile.write(f'<channel id="{channel_id}"><display-name>{name}</display-name></channel>'.encode('utf8'))

        for id, programs in frndly.guide(ids, start=int(time.time()), days=days).items():
            channel_id = f'frndly-{id}'
            for program in programs:
                start = dt.datetime.utcfromtimestamp(int(int(program['display']['markers']['startTime']['value']) / 1000)).strftime("%Y%m%d%H%M%S +0000")
                stop = dt.datetime.utcfromtimestamp(int(int(program['display']['markers']['endTime']['value']) / 1000)).strftime("%Y%m%d%H%M%S +0000")
                title = escape(program['display']['title'])
                self.wfile.write(f'<programme channel="{channel_id}" start="{start}" stop="{stop}"><title>{title}</title></programme>'.encode('utf8'))

        self.wfile.write(b'</tv>')

    def _status(self):
        self.send_response(200)
        self.send_header('content-type', 'text/html; charset=UTF-8')
        self.end_headers()
        host = self.headers.get('Host')
        self.wfile.write(f'Playlist URL: <b><a href="http://{host}/{PLAYLIST_URL}">http://{host}/{PLAYLIST_URL}</b></a><br>EPG URL: <b><a href="http://{host}/{EPG_URL}">http://{host}/{EPG_URL}</a></b>'.encode('utf8'))

class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass

if __name__ == '__main__':
    if os.getenv('IS_DOCKER'):
        PORT = 80
        USERNAME = os.getenv('USERNAME', '')
        PASSWORD = os.getenv('PASSWORD', '')
        IP = os.getenv('IP', '')
        KEEP_ALIVE_MINS = int(os.getenv('KEEP_ALIVE', 0))
    else:
        parser = argparse.ArgumentParser(description="Frndly TV for Channels")
        parser.add_argument("-u", "--USERNAME", help="Frndly TV login username (required)")
        parser.add_argument("-p", "--PASSWORD", help="Frndly TV password (required)")
        parser.add_argument("-port", "--PORT", default=80, help="Port number for server to use (optional)")
        parser.add_argument("-k", "--KEEP_ALIVE", default=0, help="Minutes between keep alive requests. 0 (default) = disable (optional)")
        parser.add_argument("-ip", "--IP", help="IP address to use (optional)")
        args = parser.parse_args()
        PORT = args.PORT
        USERNAME = args.USERNAME
        PASSWORD = args.PASSWORD
        IP = args.IP
        KEEP_ALIVE_MINS = int(args.KEEP_ALIVE)

    frndly = Frndly(USERNAME, PASSWORD, ip_addr=IP)

    def keep_alive():
        if not KEEP_ALIVE_MINS:
            return

        print("Keep alive mins: {}".format(KEEP_ALIVE_MINS))

        time.sleep(2)
        while True:
            try:
                print("Keep alive!")
                requests.get('http://127.0.0.1:{}/{}'.format(PORT, KEEP_ALIVE), timeout=20)
            except:
                pass
            time.sleep(60*KEEP_ALIVE_MINS)

    thread = threading.Thread(target=keep_alive)
    thread.daemon = True
    thread.start()

    print(f"Starting server on port {PORT}")
    server = ThreadingSimpleServer(('0.0.0.0', int(PORT)), Handler)
    server.serve_forever()
