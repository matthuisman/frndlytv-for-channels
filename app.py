#!/usr/bin/python3
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from urllib.parse import urlparse, parse_qsl

import requests

PORT = 80
USERNAME = os.getenv('USERNAME', '').strip()
PASSWORD = os.getenv('PASSWORD', '').strip()
IP_ADDR = os.getenv('IP', '').strip()

LOGO_SIZE = 110
PLAYLIST_URL = 'playlist.m3u'
PLAY_URL = 'play'
STATUS_URL = ''

HEADERS = {
    'user-agent': 'okhttp/3.12.5',
    'box-id': 'SHIELD30X8X4X0',
    'tenant-code': 'frndlytv',
}

if IP_ADDR:
    HEADERS['x-forwarded-for'] = IP_ADDR

LIVE_MAP_URL = 'https://i.mjh.nz/frndly_tv/app.json'

def login():
    if 'session-id' in HEADERS:
        data = requests.get('https://frndlytv-api.revlet.net/service/api/auth/user/info', headers=HEADERS).json()
        if data['status']:
            print('re-logged in')
            return True

    print("logging in....")

    params = {
        'box_id': HEADERS['box-id'],
        'device_id': 43,
        'tenant_code': HEADERS['tenant-code'],
        'device_sub_type': 'nvidia,8.1.0,7.4.4',
        'product': HEADERS['tenant-code'],
        'display_lang_code': 'eng',
        'timezone': 'Pacific/Auckland',
    }

    HEADERS['session-id'] = requests.get('https://frndlytv-api.revlet.net/service/api/v1/get/token', params=params, headers=HEADERS).json()['response']['sessionId']

    payload = {
        "login_key": PASSWORD,
        "login_id": USERNAME,
        "login_mode": 1,
        "os_version": "8.1.0",
        "app_version": "7.4.4",
        "manufacturer": "nvidia"
    }

    data = requests.post('https://frndlytv-api.revlet.net/service/api/auth/signin', json=payload, headers=HEADERS).json()
    if not data['status']:
        HEADERS.pop('session-id', None)
        print('Failed to login: {}'.format(data['error']['message']))
        return False
    else:
        print("logged in!")
        return True

class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self._params = {}
        super().__init__(*args, **kwargs)

    def do_GET(self):
        routes = {
            PLAYLIST_URL: self._playlist,
            PLAY_URL: self._play,
            STATUS_URL: self._status,
        }

        parsed = urlparse(self.path)
        func = parsed.path.lstrip('/')
        self._params = dict(parse_qsl(parsed.query, keep_blank_values=True))

        if func not in routes:
            self.send_response(404)
            self.end_headers()
            return

        try:
            routes[func]()
        except Exception as e:
            self._error(e)

    def _request(self, url, login_on_failure=True):
        if 'session-id' not in HEADERS:
            raise Exception('You are not logged in. Check your username / password are correct and then restart the container.')

        data = requests.get(url, headers=HEADERS).json()
        if 'response' not in data:
            if login_on_failure and login():
                return self._request(url, login_on_failure=False)

            if 'error' in data and data['error'].get('message'):
                raise Exception(data['error']['message'])
            else:
                raise Exception('Failed to get response from url: {}'.format(url))

        return data['response']

    def _error(self, message):
        self.send_response(500)
        self.end_headers()
        self.wfile.write(f'Error: {message}'.encode('utf8'))
        raise Exception(message)

    def _play(self):
        slug = self.path.split('/')[-1]
        data = self._request(f'https://frndlytv-api.revlet.net/service/api/v1/page/stream?path=channel%2Flive%2F{slug}&code=channel%2Flive%2F{slug}&include_ads=false&is_casted=true')

        try:
            requests.post('https://frndlytv-api.revlet.net/service/api/v1/stream/session/end', data={'poll_key': data['sessionInfo']['streamPollKey']}, headers=HEADERS)
        except Exception as e:
            print('failed to send end stream')

        self.send_response(302)
        self.send_header('location', data['streams'][0]['url'])
        self.end_headers()
    
    def _playlist(self):
        live_map = requests.get(LIVE_MAP_URL).json()

        rows = self._request('https://frndlytv-api.revlet.net/service/api/v1/tvguide/channels?skip_tabs=0')['data']
        if not rows:
            raise Exception('No channels returned. This is most likely due to your IP address location. Try using the IP environment variable and set it to an IP address from a supported location. eg. --env "IP=72.229.28.185" for Manhattan, New York')

        host = self.headers.get('Host')
        self.send_response(200)
        self.end_headers()

        try: start_chno = int(self._params['start_chno'])
        except: start_chno = None

        self.wfile.write(b'#EXTM3U\n')
        for row in rows:
            id = str(row['id'])
            if id not in live_map:
                print(f"Skipping {id} as not in live_map")
                continue

            name = row['display']['title']
            gracenote_id, slug = live_map[id]

            url = f'http://{host}/{PLAY_URL}/{slug}'
            bucket, path = row['display']['imageUrl'].split(',')
            logo = f'https://d229kpbsb5jevy.cloudfront.net/frndlytv/{LOGO_SIZE}/{LOGO_SIZE}/content/{bucket}/logos/{path}'

            chno = ''
            if start_chno is not None:
                chno = f' tvg-chno="{start_chno}"'
                start_chno += 1

            self.wfile.write(f'#EXTINF:-1 channel-id="frndly-{id}" tvg-logo="{logo}" tvc-guide-stationid="{gracenote_id}"{chno},{name}\n{url}\n'.encode('utf8'))

    def _status(self):
        self.send_response(200)
        self.end_headers()
        host = self.headers.get('Host')
        session_id = HEADERS.get('session-id')
        self.wfile.write(f'Playlist URL: http://{host}/{PLAYLIST_URL}\nFrndlytv Session ID: {session_id} (KEEP PRIVATE)'.encode('utf8'))

class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass

def run():
    server = ThreadingSimpleServer(('0.0.0.0', PORT), Handler)
    server.serve_forever()

if __name__ == '__main__':
    login()
    run()
