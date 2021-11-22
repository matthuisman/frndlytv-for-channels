#!/usr/bin/python3
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from urllib.parse import urlparse, parse_qsl

import requests

PORT = 80
USERNAME = os.getenv('USERNAME', '').strip()
PASSWORD = os.getenv('PASSWORD', '').strip()
IP_ADDR = os.getenv('IP', '').strip()
TIMEOUT = 15

LOGO_SIZE = 110
PLAYLIST_URL = 'playlist.m3u'
PLAY_ID = 'play'
PLAY_SLUG = 'play2'
STATUS_URL = ''

HEADERS = {
    'user-agent': 'okhttp/3.12.5',
    'box-id': 'SHIELD30X8X4X0',
    'tenant-code': 'frndlytv',
}

if IP_ADDR:
    HEADERS['x-forwarded-for'] = IP_ADDR

DATA_URL = 'https://i.mjh.nz/frndly_tv/app.json'

def login():
    if 'session-id' in HEADERS:
        data = requests.get('https://frndlytv-api.revlet.net/service/api/auth/user/info', headers=HEADERS, timeout=TIMEOUT).json()
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

    HEADERS['session-id'] = requests.get('https://frndlytv-api.revlet.net/service/api/v1/get/token', params=params, headers=HEADERS, timeout=TIMEOUT).json()['response']['sessionId']

    payload = {
        "login_key": PASSWORD,
        "login_id": USERNAME,
        "login_mode": 1,
        "os_version": "8.1.0",
        "app_version": "7.4.4",
        "manufacturer": "nvidia"
    }

    data = requests.post('https://frndlytv-api.revlet.net/service/api/auth/signin', json=payload, headers=HEADERS, timeout=TIMEOUT).json()
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

    def _error(self, message):
        self.send_response(500)
        self.end_headers()
        self.wfile.write(f'Error: {message}'.encode('utf8'))
        raise

    def do_GET(self):
        routes = {
            PLAYLIST_URL: self._playlist,
            PLAY_ID: self._play_id,
            PLAY_SLUG: self._play_slug,
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

    def _request(self, url, params=None, login_on_failure=True):
        if 'session-id' not in HEADERS:
            raise Exception('You are not logged in. Check your username / password are correct and then restart the container.')

        try:
            data = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT).json()
        except:
            data = {}

        if 'response' not in data:
            if login_on_failure and login():
                return self._request(url, login_on_failure=False)

            if 'error' in data and data['error'].get('message'):
                raise Exception(data['error']['message'])
            else:
                raise Exception('Failed to get response from url: {}'.format(url))

        return data['response']

    def _play_slug(self):
        slug = self.path.split('/')[-1]
        self._play_path(f'channel/live/{slug}')

    def _play_id(self):
        id = self.path.split('/')[-1]

        data = self._request(f'https://frndlytv-tvguideapi.revlet.net/service/api/v1/static/tvguide?channel_ids={id}&page=0')

        path = None
        cur_time = int(time.time())
        for row in data['data'][0]['programs']:
            if int(row['display']['markers']['startTime']['value']) / 1000 <= cur_time and int(row['display']['markers']['endTime']['value']) / 1000 >= cur_time:
                path = row['target']['path']
                break

        if not path:
            raise Exception(f'Unable to find live stream for: {id}. Check your time is correct')

        self._play_path(path)

    def _play_path(self, path):
        params = {
            'path': path,
            'code': path,
            'include_ads': 'false',
            'is_casted': 'true',
        }

        data = self._request(f'https://frndlytv-api.revlet.net/service/api/v1/page/stream', params=params)

        try:
            url = data['streams'][0]['url']
        except:
            raise Exception(f'Unable to find live stream for: {path}')

        print(f'{path} > {url}')

        try:
            requests.post('https://frndlytv-api.revlet.net/service/api/v1/stream/session/end', data={'poll_key': data['sessionInfo']['streamPollKey']}, headers=HEADERS, timeout=TIMEOUT)
        except Exception as e:
            print('failed to send end stream')

        self.send_response(302)
        self.send_header('location', url)
        self.end_headers()

    def _playlist(self):
        try:
            live_map = requests.get(DATA_URL, timeout=TIMEOUT).json()
        except:
            live_map = {}
            print(f'Failed to download: {DATA_URL}')

        rows = self._request('https://frndlytv-api.revlet.net/service/api/v1/tvguide/channels?skip_tabs=0')['data']
        if not rows:
            raise Exception('No channels returned. This is most likely due to your IP address location. Try using the IP environment variable and set it to an IP address from a supported location. eg. --env "IP=72.229.28.185" for Manhattan, New York')

        host = self.headers.get('Host')
        self.send_response(200)
        self.end_headers()

        start_chno = int(self._params['start_chno']) if 'start_chno' in self._params else None
        include = [x for x in self._params.get('include', '').split(',') if x]
        exclude = [x for x in self._params.get('exclude', '').split(',') if x]

        self.wfile.write(b'#EXTM3U\n')
        for row in rows:
            id = str(row['id'])
            channel_id = f'frndly-{id}'

            if (include and channel_id not in include) or (exclude and channel_id in exclude):
                print(f"Skipping {channel_id} due to include / exclude")
                continue

            try:
                slug, gracenote = live_map[id]
            except:
                slug, gracenote = None, None

            if slug:
                url = f'http://{host}/{PLAY_SLUG}/{slug}'
            else:
                url = f'http://{host}/{PLAY_ID}/{id}'

            name = row['display']['title']
            bucket, path = row['display']['imageUrl'].split(',')
            logo = f'https://d229kpbsb5jevy.cloudfront.net/frndlytv/{LOGO_SIZE}/{LOGO_SIZE}/content/{bucket}/logos/{path}'

            if gracenote:
                gracenote = ' tvc-guide-stationid="{}"'.format(gracenote)
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
