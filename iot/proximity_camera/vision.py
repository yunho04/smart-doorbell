"""Single-attempt Vision image analysis for the Spring-issued event."""
import http.client
import json
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .mqtt import valid_id


def analyze_image(config, event_id, path):
    if not valid_id(event_id):
        raise ValueError('invalid event ID')
    path = Path(path)
    content_type = mimetypes.guess_type(path.name)[0]
    if content_type not in ('image/jpeg', 'image/png'):
        raise ValueError('image must be JPEG or PNG')
    limit = min(config['max_file_bytes'], 10485760)
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError('image size out of range')
    boundary = 'doorbell' + uuid.uuid4().hex
    head = ('--%s\r\nContent-Disposition: form-data; name="image"; filename="image%s"\r\nContent-Type: %s\r\n\r\n' % (boundary, path.suffix.lower(), content_type)).encode('ascii')
    tail = ('\r\n--%s\r\nContent-Disposition: form-data; name="event_id"\r\n\r\n%s\r\n--%s--\r\n' % (boundary, event_id, boundary)).encode('ascii')
    url = urlsplit(config['vision_base_url'])
    cls = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
    conn = cls(url.hostname, url.port, timeout=config['vision_timeout_s'])
    try:
        conn.request('POST', '/vision/analyze', head + data + tail,
                     {'Content-Type': 'multipart/form-data; boundary=' + boundary})
        response = conn.getresponse()
        raw = response.read(65537)
        if not 200 <= response.status < 300 or len(raw) > 65536:
            raise RuntimeError('Vision analysis failed (HTTP %s)' % response.status)
        try:
            obj = json.loads(raw)
            if not isinstance(obj, dict) or ('event_id' in obj and
                    (not valid_id(obj['event_id']) or obj['event_id'] != event_id)):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            raise RuntimeError('invalid Vision analysis response')
        return obj
    finally:
        conn.close()
