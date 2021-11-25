#!/usr/bin/python3
import os
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qsl

from frndly import Frndly

PLAYLIST_URL = 'playlist.m3u'
PLAY = 'play'
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
            PLAY: self._play,
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

    def _play(self):
        slug = self.path.split('/')[-1]
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
        include = [x for x in self._params.get('include', '').split(',') if x]
        exclude = [x for x in self._params.get('exclude', '').split(',') if x]

        self.wfile.write(b'#EXTM3U\n')
        for row in channels:
            id = str(row['id'])
            channel_id = f'frndly-{id}'

            if (include and channel_id not in include) or (exclude and channel_id in exclude):
                print(f"Skipping {channel_id} due to include / exclude")
                continue

            data = live_map.get(id) or {}
            slug = data.get('slug') or id
            url = f'http://{host}/{PLAY}/{slug}'
            name = row['display']['title']
            logo = frndly.logo(row['display']['imageUrl'])

            if data.get('gracenote'):
                gracenote = ' tvc-guide-stationid="{}"'.format(data['gracenote'])
            else:
                gracenote = ''
                print(f'No gracenote id found in epg map for: {id}')

            chno = ''
            if start_chno is not None:
                if start_chno > 0:
                    chno = f' tvg-chno="{start_chno}"'
                    start_chno += 1

            self.wfile.write(f'#EXTINF:-1 channel-id="{channel_id}" tvg-logo="{logo}"{gracenote}{chno},{name}\n{url}\n'.encode('utf8'))

    def _status(self):
        self.send_response(200)
        self.send_header('content-type', 'text/html; charset=UTF-8')
        self.end_headers()
        host = self.headers.get('Host')
        self.wfile.write(f'Playlist URL: <b>http://{host}/{PLAYLIST_URL}</b>'.encode('utf8'))

class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Frndly TV for Channels")
    parser.add_argument("-u", "--USERNAME", help="Frndly TV login username (required)")
    parser.add_argument("-p", "--PASSWORD", help="Frndly TV password (required)")
    parser.add_argument("-port", "--PORT", default=80, help="Port number for server to use (optional)")
    parser.add_argument("-ip", "--IP", help="IP address to use (optional)")
    args = parser.parse_args()

    args.PORT = os.getenv('PORT', '') or args.PORT
    args.USERNAME = args.USERNAME or os.getenv('USERNAME', '')
    args.PASSWORD = args.PASSWORD or os.getenv('PASSWORD', '')
    args.IP = args.IP or os.getenv('IP', '')

    frndly = Frndly(args.USERNAME, args.PASSWORD, ip_addr=args.IP)
    print(f"Starting server on port {args.PORT}")
    server = ThreadingSimpleServer(('0.0.0.0', int(args.PORT)), Handler)
    server.serve_forever()
