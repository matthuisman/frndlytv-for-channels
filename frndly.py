import time
import requests

BOX_ID = 'SHIELD30X8X4X0'
TENANT_CODE = 'frndlytv'
DEVICE_ID = 43
TIMEOUT = 15
LOGO_SIZE = 400

HEADERS = {
    'user-agent': 'okhttp/3.12.5',
    'box-id': BOX_ID,
    'tenant-code': TENANT_CODE,
}

LOGO_URL = 'https://d229kpbsb5jevy.cloudfront.net/frndlytv/{size}/{size}/content/{bucket}/logos/{path}'

DATA_URL = 'https://i.mjh.nz/frndly_tv/app.json'

class Frndly(object):
    def __init__(self, username, password, ip_addr=None):
        self._username = username
        self._password = password
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        if ip_addr:
            print(f"Using IP Address: {ip_addr}")
            self._session.headers['x-forwarded-for'] = ip_addr #seems to break playback

    def logo(self, img_url, size=LOGO_SIZE):
        bucket, path = img_url.split(',')
        return LOGO_URL.format(size=size, bucket=bucket, path=path)

    def play(self, slug):
        if slug.isdigit():
            path = self._channel_path(slug)
        else:
            path = f'channel/live/{slug}'

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

        if _type.lower().strip() in ('widevine',):
            raise Exception(f'Unsupported stream type: {_type} ({url})')

        print(f'{path} > {url}')

        try:
            self._session.post('https://frndlytv-api.revlet.net/service/api/v1/stream/session/end', data={'poll_key': data['sessionInfo']['streamPollKey']}, timeout=TIMEOUT)
        except Exception as e:
            print('failed to send end stream')

        return url

    def guide(self, channel_ids, start=None, days=0):
        programs = {}
        for i in range(days):
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

    def _request(self, url, params=None, login_on_failure=True):
        if not self._session.headers.get('session-id'):
            self.login()
            login_on_failure = False

        try:
            data = self._session.get(url, params=params, timeout=TIMEOUT).json()
        except:
            data = {}

        if 'response' not in data:
            try:
                error_code = data['error']['code']
                print(error_code)
                print(data['error']['message'])
            except:
                error_code = None

            if error_code != 402 and login_on_failure and self.login():
                return self._request(url, params=params, login_on_failure=False)

            if 'error' in data and data['error'].get('message'):
                raise Exception(data['error']['message'])
            else:
                raise Exception('Failed to get response from url: {}'.format(url))

        return data['response']

    def channels(self):
        rows = self._request('https://frndlytv-api.revlet.net/service/api/v1/tvguide/channels?skip_tabs=0')['data']
        if not rows:
            raise Exception('No channels returned. This is most likely due to your IP address location. Try using the IP environment variable and set it to an IP address from a supported location. eg. --env "IP=72.229.28.185" for Manhattan, New York')

        return rows

    def live_map(self):
        try:
            return self._session.get(DATA_URL, timeout=TIMEOUT).json()
        except:
            print(f'Failed to download: {DATA_URL}')
            return {}

    def login(self):
        print("logging in....")
        self._session.headers.pop('session-id', None)

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

        session_id = self._session.get('https://frndlytv-api.revlet.net/service/api/v1/get/token', params=params, timeout=TIMEOUT).json()['response']['sessionId']

        payload = {
            "login_id": self._username,
            "login_key": self._password,
            "login_mode": 1,
            "os_version": "8.1.0",
            "app_version": "7.4.4",
            "manufacturer": "nvidia"
        }

        data = self._session.post('https://frndlytv-api.revlet.net/service/api/auth/signin', json=payload, headers={'session-id': session_id}, timeout=TIMEOUT).json()
        if not data['status']:
            raise Exception('Failed to login: {}'.format(data['error']['message']))

        print("Logged in!")
        self._session.headers['session-id'] = session_id
        return True
