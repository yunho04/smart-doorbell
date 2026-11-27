"""가상 Vision: 테스트용 대표 이미지를 만들고 Spring 에 업로드한다 (외부 라이브러리 없이 PNG 생성)."""
import struct
import zlib

RISK_COLORS = {"LOW": (46, 160, 67), "MEDIUM": (227, 160, 8), "HIGH": (207, 34, 46)}
PERSON = (30, 30, 40)


def make_test_image(event_id, risk_level, width=480, height=360):
    """위험도 색 배경 + 사람 실루엣. 상단 띠 색은 eventId 로 정해져 이벤트마다 바이트가 다르다."""
    background = RISK_COLORS.get(risk_level, (120, 120, 120))
    band = ((event_id * 53) % 256, (event_id * 97) % 256, (event_id * 151) % 256)
    cx, head_y, head_r = width / 2, height * 0.36, height * 0.14
    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            if y < 24:
                color = band
            elif (x - cx) ** 2 + (y - head_y) ** 2 <= head_r ** 2:
                color = PERSON
            elif y > height * 0.56 and abs(x - cx) < width * 0.2:
                color = PERSON
            else:
                color = background
            row += bytes(color)
        rows.append(bytes(row))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows)))
            + chunk(b"IEND", b""))


def upload_representative(api, event_id, image):
    """ai-server/vision/app.py 와 같은 경로: POST /api/v1/events/{id}/representative-image (multipart 키 file)."""
    return api.upload_representative_image(event_id, image, "representative.png", "image/png")
