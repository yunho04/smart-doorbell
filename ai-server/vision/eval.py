"""Vision 성능 측정 (학습 아님). 위키미디어 커먼즈 공개 사진으로 라벨별 검출률·오탐률을 잰다.

python eval.py fetch   # eval/ 에 분류별 사진 받기 (분류당 최대 8장, 640px 썸네일, 출처·라이선스는 eval/manifest.csv)
python eval.py         # 측정: 기대 라벨을 몇 장에서 잡았나(기준값별) + 정상 사진에서 흉기·얼굴 가림 오탐
한계: 사진 1장씩 본다 (실제 서버는 같은 라벨이 2장 이상 나와야 인정). 현관 카메라 각도·조명과 다르다.
"""
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

EVAL = Path(__file__).parent / "eval"
UA = {"User-Agent": "doorbell-vision-eval/0.1 (student class project)"}
CATS = {  # 폴더: (커먼즈 분류, 기대 라벨. None = 평범한 사람 → 오탐 확인용)
    "knife": ("Category:People holding knives", "knife"),
    "knife_hand": ("Category:Human hands holding knives", "knife"),
    "mask_m": ("Category:Males in masks in the United States", "face mask"),
    "mask_f": ("Category:Female people in masks in the United States", "face mask"),
    "helmet": ("Category:Women wearing motorcycle helmets", "helmet"),
    "balaclava": ("Category:Balaclavas (clothing)", "balaclava"),
    "phone": ("Category:People using mobile phones", None),
    "umbrella": ("Category:People with umbrellas", None),
    "normal": (None, None),  # ultralytics 예제 사진(bus·zidane): 흉기 없는 사람들
}
PER_CAT = 8
# Hugging Face 공개 데이터셋 (연락처 없이 받을 수 있음). 폴더: (데이터셋, 고르는 법, 기대 라벨). 라이선스는 각 데이터셋 README
HF_SETS = {
    "cctv_knife": ("Simuletic/cctv-knife-detection-dataset", "Knife_Dataset/images/", "knife"),  # 합성 CCTV, CC BY 4.0
    "chips": ("Simuletic/Weapon_Detection_Dataset_Handgun_vs_BagOfChips", "Handgun_vs_BagOfChips/images/doritos", None),
    "umbrella_cctv": ("Simuletic/CCTV_Weapon_Detection_Rifles_vs_Umbrellas", "umbrella", None),  # 라벨에 weapon 없는 사진만
    "mask_on": ("HuangYiYang/Face-Mask-Detection-Dataset", 0, "face mask"),  # MIT, label 0 = with_mask
    "mask_off": ("HuangYiYang/Face-Mask-Detection-Dataset", 1, None),
}
HF_N = {"cctv_knife": 12, "chips": 12, "umbrella_cctv": 10, "mask_on": 15, "mask_off": 15}


def get(url, wait=5):
    time.sleep(wait)  # 위키미디어 요청 제한(429) 피하기. Hugging Face 는 0.5초면 충분
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()


def fetch():
    EVAL.mkdir(exist_ok=True)
    rows = []
    import shutil
    import ultralytics
    (EVAL / "normal").mkdir(exist_ok=True)
    for name in ["bus.jpg", "zidane.jpg"]:
        shutil.copy(Path(ultralytics.__file__).parent / "assets" / name, EVAL / "normal" / name)
    for key, (cat, _) in CATS.items():
        if cat is None:
            continue
        q = urllib.parse.urlencode({"action": "query", "format": "json", "generator": "categorymembers",
                                    "gcmtitle": cat, "gcmtype": "file", "gcmlimit": 30, "prop": "imageinfo",
                                    "iiprop": "url|extmetadata|mime", "iiurlwidth": 640})
        pages = json.loads(get("https://commons.wikimedia.org/w/api.php?" + q)).get("query", {}).get("pages", {})
        jpgs = [p for p in pages.values() if p["imageinfo"][0]["mime"] == "image/jpeg"][:PER_CAT]
        (EVAL / key).mkdir(exist_ok=True)
        for i, p in enumerate(jpgs):
            info = p["imageinfo"][0]
            meta = info.get("extmetadata", {})
            name = f"{i:02d}.jpg"
            if not (EVAL / key / name).exists():  # 다시 돌리면 받은 것은 건너뜀
                try:
                    (EVAL / key / name).write_bytes(get(info["thumburl"]))
                except urllib.error.HTTPError as ex:
                    print(f"{key}/{name} 받기 실패 {ex.code}, 나중에 다시 돌리면 이어서 받음")
                    continue
            rows.append([f"{key}/{name}", cat, info["descriptionurl"],
                         meta.get("LicenseShortName", {}).get("value", ""),
                         meta.get("Artist", {}).get("value", "")[:120]])
        print(f"{key:11s} {len(jpgs)}장  ({cat})")
    with open(EVAL / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["file", "category", "source", "license", "artist"], *rows])


def fetch_hf():
    import cv2
    import numpy as np

    def get(url):
        return globals()["get"](url, wait=0.5)

    def save(folder, i, url):  # 큰 PNG도 긴 변 1280 JPEG로 줄여 저장. 이미 있으면 안 받음
        target = EVAL / folder / f"{i:02d}.jpg"
        if target.exists():
            return
        im = cv2.imdecode(np.frombuffer(get(url), np.uint8), cv2.IMREAD_COLOR)
        s = min(1.0, 1280 / max(im.shape[:2]))
        _, buf = cv2.imencode(".jpg", cv2.resize(im, None, fx=s, fy=s), [cv2.IMWRITE_JPEG_QUALITY, 90])
        target.write_bytes(buf.tobytes())  # cv2.imwrite 는 한글 경로에서 조용히 실패한다

    rows = []
    for folder, (ds, pick, _) in HF_SETS.items():
        (EVAL / folder).mkdir(parents=True, exist_ok=True)
        n, got = HF_N[folder], 0
        try:
            got = fetch_set(folder, ds, pick, n, save, rows)
        except urllib.error.HTTPError as ex:  # 한 묶음이 실패해도 나머지와 출처 기록은 남긴다
            print(f"{folder:14s} 실패 {ex.code}")
            continue
        print(f"{folder:14s} {got}장  ({ds})")
    with open(EVAL / "manifest_hf.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["file", "dataset", "source"], *rows])


def fetch_set(folder, ds, pick, n, save, rows):
    """같은 순서로 고르므로 다시 돌려도 같은 사진. 받은 장수를 돌려준다."""
    def get(url):
        return globals()["get"](url, wait=0.5)

    got = 0
    if isinstance(pick, int):  # 라벨이 붙은 표 형태: datasets-server rows API 를 100줄씩 넘기며 그 라벨만
        for offset in range(0, 4000, 100):
            q = urllib.parse.urlencode({"dataset": ds, "config": "default", "split": "train", "offset": offset, "length": 100})
            page = json.loads(get("https://datasets-server.huggingface.co/rows?" + q))["rows"]
            for r in page:
                if r["row"]["label"] == pick and got < n:
                    save(folder, got, r["row"]["image"]["src"])
                    rows.append([f"{folder}/{got:02d}.jpg", ds, f"row {r['row_idx']}"])
                    got += 1
            if got >= n or not page:
                break
        return got
    # 파일 형태: 저장소 파일 목록에서 고름
    files = json.loads(get(f"https://huggingface.co/api/datasets/{ds}/tree/main?recursive=true"))
    for path in sorted(f["path"] for f in files if f["type"] == "file" and "/images/" in f["path"]):
        if got >= n:
            break
        if pick == "umbrella":  # 라벨 파일에 weapon(1)이 없어야 우산 사진
            label = get(f"https://huggingface.co/datasets/{ds}/resolve/main/"
                        + path.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt").decode()
            if any(line.split()[0] == "1" for line in label.splitlines() if line.strip()):
                continue
        elif not path.startswith(pick):
            continue
        save(folder, got, f"https://huggingface.co/datasets/{ds}/resolve/main/{path}")
        rows.append([f"{folder}/{got:02d}.jpg", ds, path])
        got += 1
    return got


def measure():
    import cv2
    import app  # 서버와 같은 모델·라벨·기준값

    expect = {k: v[1] for k, v in CATS.items()} | {k: v[2] for k, v in HF_SETS.items()}
    best = {}  # file -> {label: 최고 신뢰도}
    for key in expect:
        for img in sorted((EVAL / key).glob("*.jpg")):
            frame = cv2.imread(str(img))
            boxes = app.model.predict(frame, conf=0.1, verbose=False)[0].boxes
            seen = {}
            for c, p in zip(boxes.cls.tolist(), boxes.conf.tolist()):
                label = app.model.names[int(c)]
                seen[label] = max(seen.get(label, 0), p)
            best[f"{key}/{img.name}"] = seen

    print("\n## 기대 라벨 검출률 (기준값별)        지금 기준값 = *")
    thresholds = [0.2, 0.3, 0.4, 0.5, 0.6]
    print(f"{'분류':12s} {'라벨':12s} " + " ".join(f"{t:>5}" for t in thresholds))
    for key, want in expect.items():
        files = [f for f in best if f.startswith(key + "/")]
        if not want or not files:
            continue
        cells = [f"{sum(best[f].get(want, 0) >= t for f in files)}/{len(files)}"
                 + ("*" if abs(t - app.CLASSES[want]) < 1e-9 else " ") for t in thresholds]
        print(f"{key:12s} {want:12s} " + " ".join(f"{c:>5}" for c in cells))

    print("\n## 오탐: 그 라벨이 없어야 할 사진에서 지금 기준값을 넘은 장수")
    for label in ["knife", "baseball bat", "helmet", "face mask", "balaclava"]:
        others = [f for f in best if expect[f.split("/")[0]] != label]
        hits = [f for f in others if best[f].get(label, 0) >= app.CLASSES[label]]
        conf = ", ".join(f"{f}({best[f][label]:.2f})" for f in hits[:6])
        print(f"{label:12s} {len(hits)}/{len(others)}  {conf}")


if __name__ == "__main__":
    {"fetch": fetch, "fetch-hf": fetch_hf}.get((sys.argv[1:] or [""])[0], measure)()
