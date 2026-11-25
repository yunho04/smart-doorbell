"""Bounded single-attempt Spring representative-image upload."""
import http.client
import json
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from .mqtt import valid_id


class SpringIntegration:
    def __init__(self, config, events, event_factory=None):
        self.config, self.events = config, events
        if event_factory is None:
            from .mqtt import EventClient
            event_factory = EventClient
        self.event_factory = event_factory

    def reconnect(self):
        self.events.close()
        self.events = self.event_factory(self.config)
        self.events.start()

    def create_event(self, request_id, distance_cm):
        return self.events.create_event(request_id, distance_cm)

    def upload(self, event_id, path, request_id, finish=True):
        self.events.check()
        upload_image(self.config, event_id, path)
        self.events.check()
        if finish:
            self.events.finish()

    def abort(self):
        self.events.abort()

    def close(self):
        self.events.close()


def upload_image(config, event_id, path):
    if not valid_id(event_id):
        raise ValueError('invalid event ID')
    path = Path(path)
    content_type = mimetypes.guess_type(path.name)[0]
    if content_type not in ('image/jpeg', 'image/png'):
        raise ValueError('image must be JPEG or PNG')
    with path.open('rb') as stream:
        data = stream.read(min(config['max_file_bytes'], 10485760) + 1)
    if not data or len(data) > min(config['max_file_bytes'], 10485760):
        raise ValueError('image size out of range')
    boundary = 'doorbell' + uuid.uuid4().hex
    head = ('--%s\r\nContent-Disposition: form-data; name="file"; filename="image%s"\r\nContent-Type: %s\r\n\r\n' % (boundary, path.suffix.lower(), content_type)).encode('ascii')
    body = head + data + ('\r\n--%s--\r\n' % boundary).encode('ascii')
    url = urlsplit(config['spring_base_url'])
    connection_class = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
    conn = connection_class(url.hostname, url.port, timeout=config['http_timeout_s'])
    try:
        conn.request('POST', '/api/v1/events/%s/image' % event_id, body,
                     {'Content-Type': 'multipart/form-data; boundary=' + boundary})
        response = conn.getresponse()
        result = response.read(65537)
        if response.status != 201 or len(result) > 65536:
            raise RuntimeError('Spring image upload failed (HTTP %s)' % response.status)
        try:
            obj = json.loads(result)
            if (not isinstance(obj, dict) or not valid_id(obj.get('mediaId')) or
                    not valid_id(obj.get('eventId')) or obj['eventId'] != event_id or
                    obj.get('mediaType') != 'IMAGE' or not isinstance(obj.get('filePath'), str) or not obj['filePath'].strip()):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            raise RuntimeError('invalid Spring image response')
    finally:
        conn.close()


def get_event_status(config, event_id):
    if not valid_id(event_id):
        raise ValueError('invalid event ID')
    url = urlsplit(config['spring_base_url'])
    cls = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
    conn = cls(url.hostname, url.port, timeout=config['session_status_timeout_s'])
    try:
        conn.request('GET', '/api/v1/events/%s' % event_id)
        response = conn.getresponse()
        data = response.read(65537)
        if response.status != 200 or len(data) > 65536:
            raise RuntimeError('Spring event lookup failed (HTTP %s)' % response.status)
        try:
            obj = json.loads(data)
            if (not isinstance(obj, dict) or not valid_id(obj.get('eventId')) or obj['eventId'] != event_id or
                not valid_id(obj.get('deviceId')) or obj['deviceId'] != config['device_id'] or
                obj.get('status') not in ('DETECTED', 'ANALYZING', 'COMPLETED')):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            raise RuntimeError('invalid Spring event response')
        return obj['status']
    finally:
        conn.close()
