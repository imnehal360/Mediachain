"""Generate original synthetic speech + diagram media using espeak (Linux) or say (macOS).

The script's text/diagram are MIT licensed with this repository. No downloaded media is used.
"""

import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

TEXT = "Artificial intelligence connects data and reasoning. On the screen, data flows into a model, and the model produces a prediction."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".mediachain/fixture"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    audio = args.output / "speech.wav"
    if shutil.which("espeak"):
        subprocess.run(["espeak", "-w", str(audio), "-s", "140", TEXT], check=True)
    elif shutil.which("say"):
        aiff = args.output / "speech.aiff"
        subprocess.run(["say", "-o", str(aiff), TEXT], check=True)
        subprocess.run(["ffmpeg", "-y", "-i", str(aiff), str(audio)], check=True)
    else:
        raise SystemExit(
            "Install espeak, or record the supplied TEXT as speech.wav, then generate your video with FFmpeg."
        )
    image = Image.new("RGB", (1280, 720), "#101c32")
    draw = ImageDraw.Draw(image)
    draw.text((60, 70), "ARTIFICIAL INTELLIGENCE", fill="white", font_size=44)
    for x, label in [(80, "DATA"), (500, "MODEL"), (920, "PREDICTION")]:
        draw.rounded_rectangle((x, 280, x + 280, 440), radius=20, outline="#65d6ff", width=5)
        draw.text((x + 25, 340), label, fill="white", font_size=30)
    for x in (380, 800):
        draw.line((x, 360, x + 90, 360), fill="#65d6ff", width=8)
        draw.polygon([(x + 90, 360), (x + 70, 347), (x + 70, 373)], fill="#65d6ff")
    frame = args.output / "diagram.png"
    image.save(frame)
    video = args.output / "lecture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(frame),
            "-i",
            str(audio),
            "-c:v",
            "libx264",
            "-tune",
            "stillimage",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            str(video),
        ],
        check=True,
    )
    print(video)


if __name__ == "__main__":
    main()
