import os
import time
import requests

BOX_ID = 'SHIELD30X8X4X0'
TENANT_CODE = 'frndlytv'
DEVICE_ID = 43
TIMEOUT = 15
LOGO_SIZE = 400
FORCE_LOGIN = 60*60*5 #force login after 5 hours

HEADERS = {
    'user-agent': 'okhttp/3.12.5',
    'box-id': BOX_ID,
    'tenant-code': TENANT_CODE,
}

LOGO_URL = 'https://d229kpbsb5jevy.cloudfront.net/frndlytv/{size}/{size}/content/{bucket}/logos/{path}'

DATA_URL = 'https://i.mjh.nz/frndly_tv/app.json'

class Frndly(object):
    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._headers = {}
        self._headers.update(HEADERS)
        self._live_map = {}
        self._last_login = 0

    def logo(self, img_url, size=LOGO_SIZE):
        bucket, path = img_url.split(',')
        return LOGO_URL.format(size=size, bucket=bucket, path=path)

    def _channel_path(self, channel_id):
        path = None
        cur_time = int(time.time())

        data = self.guide([channel_id,])
        for row in data.get(channel_id, []):
            if int(row['display']['markers']['startTime']['value']) / 1000 <= cur_time and int(row['display']['markers']['endTime']['value']) / 1000 >= cur_time:
                path = row['target']['path']
                break

        if not path:
            raise Exception(f'Unable to find live stream for: {channel_id}. Check your time is correct')

        return path

    def _get_play_url(self, path):
        params = {
            'path': path,
            'code': path,
            'include_ads': 'false',
            'is_casted': 'true',
        }

        data = self._request(f'https://frndlytv-api.revlet.net/service/api/v1/page/stream', params=params)

        try:
            stream = data['streams'][0]
            url = stream['url']
            _type = stream['streamType']
        except:
            raise Exception(f'Unable to find live stream for: {path}')

        try:
            url += '&start={0}&startTime={0}'.format(int(int(data['playerSettings'][0]['value'])/1000))
        except:
            pass

        if _type.lower().strip() in ('widevine',):
            raise Exception(f'Unsupported stream type: {_type} ({url})')

        print(f'{path} > {url}')
        try:
            requests.post('https://frndlytv-api.revlet.net/service/api/v1/stream/session/end', data={'poll_key': data['sessionInfo']['streamPollKey']}, headers=self._headers, timeout=TIMEOUT)
        except Exception as e:
            print(f'Failed to send end stream {e}')

        return url

    def play(self, slug):
        if slug.isdigit():
            id = slug
        else:
            slug, id = slug.rsplit('-', 1)
            try:
                return self._get_play_url(f'channel/live/{slug}')
            except Exception:
                print(f"Failed to play via slug {slug}. Fallback to ID")

        print(f"Attempting playback using ID {id}")
        path = self._channel_path(id)
        return self._get_play_url(path)

    def guide(self, channel_ids, start=None, days=1):
        programs = {}
        for _ in range(days):
            params = {
                'channel_ids': ','.join(channel_ids),
                'page': 0,
            }

            if start:
                end = start+86400
                params['start_time'] = start*1000
                params['end_time'] = end*1000
                start = end

            for row in self._request(f'https://frndlytv-tvguideapi.revlet.net/service/api/v1/static/tvguide', params=params)['data']:
                channel_id = str(row['channelId'])
                if channel_id not in programs:
                    programs[channel_id] = []
                programs[channel_id].extend(row['programs'])

        return programs

    def _request(self, url, params=None, **kwargs):
        for _ in range(3):
            try:
                print(f"Requesting: {url}")
                data = requests.get(url, params=params, headers=self._headers, timeout=TIMEOUT, **kwargs).json()

                if 'response' in data:
                    return data['response']

                try:
                    error_code = data['error']['code']
                    print(error_code)
                    print(data['error']['message'])
                    # dont retry on 404s
                    if error_code == 404:
                        break
                except:
                    error_code = None

                self.login()
            except Exception as e:
                print(e)

        raise Exception('Failed to get response from url: {}'.format(url))

    def keep_alive(self):
        # Force login after X hours
        if (time.time() - self._last_login) > FORCE_LOGIN:
            print("Forcing login!")
            self.login()
        self.channels()

    def channels(self):
        rows = self._request('https://frndlytv-api.revlet.net/service/api/v1/tvguide/channels?skip_tabs=0')['data']
        if not rows:
            msg = 'No channels returned. This is most likely due to your IP address location.'
            if os.getenv('IS_DOCKER'):
                msg += ' You can spoof an IP address for a supported location using IP environment variable. eg. --env "IP=72.229.28.185" for Manhattan, New York.'
            else:
                msg += ' You can spoof an IP address for a supported location using IP cmdline argument. eg. --IP 72.229.28.185 for Manhattan, New York.'
            msg += ' This may not work with all channels.'
            raise Exception(msg)

        return [x for x in rows if not x.get('metadata',{}).get('isChannelBanner', '')]

    def live_map(self):
        try:
            self._live_map = requests.get(DATA_URL, timeout=TIMEOUT).json()
        except:
            print(f'Failed to download: {DATA_URL}')

        return self._live_map

    def login(self):
        print("logging in....")
        if not self._username or not self._password:
            raise Exception('USERNAME and PASSWORD are required')

        params = {
            'box_id': BOX_ID,
            'device_id': DEVICE_ID,
            'tenant_code': TENANT_CODE,
            'device_sub_type': 'nvidia,8.1.0,7.4.4',
            'product': TENANT_CODE,
            'display_lang_code': 'eng',
            'timezone': 'Pacific/Auckland',
        }

        headers = {i: self._headers[i] for i in self._headers if i != 'session-id'}
        headers['session-id'] = requests.get('https://frndlytv-api.revlet.net/service/api/v1/get/token', params=params, headers=headers, timeout=TIMEOUT).json()['response']['sessionId']

        payload = {
            "login_id": self._username,
            "login_key": self._password,
            "login_mode": 1,
            "os_version": "8.1.0",
            "app_version": "7.4.4",
            "manufacturer": "nvidia"
        }

        data = requests.post('https://frndlytv-api.revlet.net/service/api/auth/signin', json=payload, headers=headers, timeout=TIMEOUT).json()
        if not data['status']:
            raise Exception('Failed to login: {}'.format(data['error']['message']))

        print("Logged in!")
        self._last_login = time.time() - 10
        time.sleep(1)
        self._headers = headers
        return True
