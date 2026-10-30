import asyncio, json, os, subprocess, textwrap
import requests, edge_tts

KEY = os.environ["GEMINI_API_KEY"]
VOICE = "en-US-GuyNeural"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
USED = "used_topics.json"
OUT = "out"


def pick_model():
    r = requests.get(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={KEY}", timeout=30)
    r.raise_for_status()
    bad = ("lite", "image", "tts", "live", "audio", "exp", "preview")
    names = [m["name"].split("/")[-1] for m in r.json()["models"]
             if "generateContent" in m.get("supportedGenerationMethods", [])
             and "flash" in m["name"] and not any(b in m["name"] for b in bad)]
    return "gemini-flash-latest" if "gemini-flash-latest" in names else sorted(names)[-1]


MODEL = pick_model()
print("Using model:", MODEL)


def get_script():
    used = json.load(open(USED)) if os.path.exists(USED) else []
    prompt = (
        "You write 30-second TikTok scripts about microcontrollers "
        "(Arduino, ESP32, sensors, tiny projects, beginner tips). "
        f"Do NOT repeat these topics: {used[-30:]}. "
        'Reply ONLY with JSON: {"topic": str, "caption": str (with 4 hashtags), '
        '"lines": [5-7 short sentences, max 12 words each, first one a hook]}'
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    for attempt in range(3):
        try:
            r = requests.post(url, json=body, timeout=180)
            r.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            print("Gemini attempt", attempt + 1, "failed:", e)
            if attempt == 2:
                raise
    data = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    used.append(data["topic"])
    json.dump(used, open(USED, "w"), indent=1)
    return data


def duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", path])
    return float(out)


async def make_clip(i, line):
    mp3, txt, clip = f"{OUT}/{i}.mp3", f"{OUT}/{i}.txt", f"{OUT}/{i}.mp4"
    await asyncio.wait_for(edge_tts.Communicate(line, VOICE).save(mp3), timeout=60)
    open(txt, "w").write(textwrap.fill(line, 20))
    d = duration(mp3) + 0.3
    vf = (f"drawtext=fontfile={FONT}:textfile={txt}:fontcolor=white:fontsize=72:"
          "line_spacing=14:x=(w-text_w)/2:y=(h-text_h)/2")
    subprocess.check_call([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=0x0b1f3a:s=1080x1920:r=30:d={d}",
        "-i", mp3, "-vf", vf, "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", clip])
    return clip


async def main():
    os.makedirs(OUT, exist_ok=True)
    data = get_script()
    clips = [await make_clip(i, l) for i, l in enumerate(data["lines"])]
    with open(f"{OUT}/list.txt", "w") as f:
        for c in clips:
            f.write(f"file '{os.path.basename(c)}'\n")
    subprocess.check_call([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", f"{OUT}/list.txt", "-c", "copy", f"{OUT}/video.mp4"])
    open(f"{OUT}/caption.txt", "w").write(data["caption"])
    print("Done:", data["topic"])


asyncio.run(main())
