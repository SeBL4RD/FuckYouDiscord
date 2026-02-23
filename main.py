#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Video Converter
Convertit les vidéos en H.264 MP4 sous 10 MB pour Discord.
Stratégie : réduction résolution d'abord, puis qualité si déjà en 720p ou moins.
"""

import sys
import os
import subprocess
import json
import zipfile
import urllib.request
import shutil
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent.resolve()
FFMPEG_DIR  = SCRIPT_DIR / "ffmpeg"
FFMPEG_EXE  = FFMPEG_DIR / "ffmpeg.exe"
FFPROBE_EXE = FFMPEG_DIR / "ffprobe.exe"
OUTPUT_DIR  = SCRIPT_DIR / "output"

TARGET_SIZE_MB = 9.5   # marge sous la limite Discord de 10 MB
AUDIO_BITRATE  = 128   # kbps

FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

# Ladder résolution : (hauteur, bitrate_vidéo_min_kbps pour que ce soit lisible)
RESOLUTION_LADDER = [
    (1080, 2000),
    ( 720,  800),
    ( 480,  400),
    ( 360,  200),
]

# ── Setup FFmpeg ───────────────────────────────────────────────────────────────
def _dl_progress(count, block, total):
    pct    = min(100, int(count * block * 100 / total))
    filled = pct // 2
    bar    = "█" * filled + "░" * (50 - filled)
    print(f"\r  [{bar}] {pct}%", end="", flush=True)

def setup_ffmpeg():
    if FFMPEG_EXE.exists() and FFPROBE_EXE.exists():
        return

    print("FFmpeg introuvable — téléchargement (~120 MB, une seule fois)...")
    FFMPEG_DIR.mkdir(exist_ok=True)
    tmp = SCRIPT_DIR / "_ffmpeg_tmp.zip"

    try:
        urllib.request.urlretrieve(FFMPEG_URL, tmp, reporthook=_dl_progress)
        print()
        print("Extraction des binaires FFmpeg...")
        with zipfile.ZipFile(tmp) as z:
            for member in z.namelist():
                name = Path(member).name
                if name in ("ffmpeg.exe", "ffprobe.exe"):
                    dest = FFMPEG_DIR / name
                    dest.write_bytes(z.read(member))
        print("FFmpeg prêt !\n")
    finally:
        if tmp.exists():
            tmp.unlink()

# ── Analyse de la vidéo ────────────────────────────────────────────────────────
def probe(path: Path) -> dict:
    cmd = [
        str(FFPROBE_EXE), "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe a échoué :\n{r.stderr}")
    return json.loads(r.stdout)

def get_video_stream(info: dict) -> dict:
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            return s
    raise RuntimeError("Aucun flux vidéo trouvé dans ce fichier.")

# ── Choix de la résolution ─────────────────────────────────────────────────────
def pick_resolution(src_height: int, video_kbps: int) -> int:
    """
    Retourne la meilleure hauteur de sortie selon le bitrate disponible.
    Priorité : baisser la résolution avant de sacrifier la qualité.
    """
    for height, min_kbps in RESOLUTION_LADDER:
        if height <= src_height and video_kbps >= min_kbps:
            return height
    return 360  # dernier recours

# ── Encodage deux passes ───────────────────────────────────────────────────────
def encode_two_pass(src: Path, dst: Path, height: int, video_kbps: int, has_audio: bool):
    """
    Encodage H.264 deux passes avec bitrate cible.
    Plus précis qu'un encodage simple pour tenir dans une taille donnée.
    """
    scale   = f"scale=-2:{height}"
    passlog = str(SCRIPT_DIR / "_ffmpeg2pass")
    null    = "NUL" if os.name == "nt" else "/dev/null"
    base    = [str(FFMPEG_EXE), "-hide_banner", "-y", "-i", str(src)]

    # ── Passe 1 : analyse ────────────────────────────────────────────────────
    print("  Passe 1/2  (analyse)...")
    p1 = base + [
        "-vf", scale,
        "-c:v", "libx264", "-preset", "slow",
        "-b:v", f"{video_kbps}k",
        "-pass", "1", "-passlogfile", passlog,
        "-an", "-f", "null", null,
    ]
    r = subprocess.run(p1, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Erreur passe 1 :\n{r.stderr[-1000:]}")

    # ── Passe 2 : encodage ───────────────────────────────────────────────────
    print("  Passe 2/2  (encodage)...")
    p2 = base + [
        "-vf", scale,
        "-c:v", "libx264", "-preset", "slow",
        "-b:v", f"{video_kbps}k",
        "-pass", "2", "-passlogfile", passlog,
        "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        p2 += ["-c:a", "aac", "-b:a", f"{AUDIO_BITRATE}k"]
    else:
        p2 += ["-an"]
    p2 += ["-movflags", "+faststart", str(dst)]

    r = subprocess.run(p2)   # progression visible dans le terminal
    if r.returncode != 0:
        raise RuntimeError("L'encodage a échoué (voir message ci-dessus).")

    # Nettoyage fichiers log de passe
    for f in SCRIPT_DIR.glob("_ffmpeg2pass*"):
        try:
            f.unlink()
        except OSError:
            pass

# ── Chemin de sortie unique ────────────────────────────────────────────────────
def unique_output(src_name: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    stem = Path(src_name).stem
    dst  = OUTPUT_DIR / f"{stem}_discord.mp4"
    n    = 1
    while dst.exists():
        dst = OUTPUT_DIR / f"{stem}_discord_{n}.mp4"
        n  += 1
    return dst

# ── Traitement d'un fichier ────────────────────────────────────────────────────
def process(input_path: str):
    src = Path(input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Fichier introuvable : {src}")

    size_mb = src.stat().st_size / (1024 ** 2)

    print(f"\nFichier  : {src.name}")
    print(f"Taille   : {size_mb:.1f} MB")

    info      = probe(src)
    vs        = get_video_stream(info)
    duration  = float(info["format"]["duration"])
    src_w     = vs["width"]
    src_h     = vs["height"]
    src_codec = vs.get("codec_name", "?")
    has_audio = any(
        s.get("codec_type") == "audio" for s in info.get("streams", [])
    )

    print(f"Durée    : {duration:.1f}s  |  {src_w}×{src_h}  |  codec : {src_codec}")

    # ── Déjà compatible Discord ? ────────────────────────────────────────────
    if (size_mb <= 10.0
            and src_codec == "h264"
            and src.suffix.lower() == ".mp4"):
        print("Déjà compatible Discord (≤ 10 MB, H.264, .mp4) — copie directe.")
        dst = unique_output(src.name)
        shutil.copy2(src, dst)
        print(f"→ {dst}")
        return

    # ── Calcul du bitrate cible ───────────────────────────────────────────────
    target_bits = TARGET_SIZE_MB * 8 * 1024 * 1024
    audio_bits  = (AUDIO_BITRATE * 1000 * duration) if has_audio else 0
    video_bits  = target_bits - audio_bits

    if video_bits <= 0:
        raise RuntimeError(
            f"Vidéo trop longue ({duration:.0f}s) pour tenir dans "
            f"{TARGET_SIZE_MB} MB avec audio à {AUDIO_BITRATE} kbps.\n"
            "Conseil : découpez la vidéo en segments plus courts."
        )

    video_kbps = int(video_bits / duration / 1000)

    # ── Choix de la résolution ────────────────────────────────────────────────
    # Priorité : baisser la résolution avant de baisser la qualité
    target_h  = pick_resolution(src_h, video_kbps)
    target_h  = min(target_h, src_h)     # jamais d'upscale
    target_h -= target_h % 2             # H.264 requiert dimensions paires

    print(f"\nStratégie de compression :")
    print(f"  Bitrate vidéo cible  : {video_kbps} kbps")
    if target_h < src_h:
        print(f"  Résolution           : {src_h}p → {target_h}p (réduite pour tenir dans 10 MB)")
    else:
        print(f"  Résolution           : {target_h}p (conservée, seule la qualité réduite)")

    dst = unique_output(src.name)
    print(f"\nEncodage → {dst.name}")
    encode_two_pass(src, dst, target_h, video_kbps, has_audio)

    out_mb = dst.stat().st_size / (1024 ** 2)
    ok     = out_mb <= 10.0

    print()
    print("─" * 60)
    if ok:
        print(f"  OK  Taille finale : {out_mb:.2f} MB  (≤ 10 MB)")
    else:
        print(f"  ⚠   Taille finale : {out_mb:.2f} MB  (légèrement au-dessus de 10 MB)")
        print("      Contenu trop complexe pour cette durée — essayez de couper la vidéo.")
    print(f"  Fichier : {dst}")
    print("─" * 60)

# ── Point d'entrée ─────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Discord Video Converter")
    print("  H.264 MP4  |  ≤ 10 MB  |  Prêt pour Discord")
    print("=" * 60)

    if len(sys.argv) < 2:
        print("\nUsage : glissez-déposez une ou plusieurs vidéos sur le .bat")
        print("Formats acceptés : MP4, MKV, AVI, MOV, WebM, etc.")
        input("\nAppuyez sur Entrée pour quitter...")
        return

    try:
        setup_ffmpeg()
    except Exception as exc:
        print(f"\n[ERREUR setup FFmpeg] {exc}")
        input("\nAppuyez sur Entrée pour quitter...")
        sys.exit(1)

    errors = []
    for arg in sys.argv[1:]:
        try:
            process(arg)
        except Exception as exc:
            print(f"\n[ERREUR] {exc}")
            errors.append(arg)

    print()
    if errors:
        print(f"Terminé avec {len(errors)} erreur(s).")
    else:
        print("Toutes les vidéos ont été converties avec succès !")
    input("\nAppuyez sur Entrée pour quitter...")

if __name__ == "__main__":
    main()
