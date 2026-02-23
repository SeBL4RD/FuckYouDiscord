# Discord Video Converter

A drag-and-drop tool that automatically converts videos to a Discord-compatible format — H.264 MP4 under 10 MB — so they play inline in chat without any hassle.

## How to use

1. Drop one or several video files onto `fuckYouDiscord.bat`
2. Converted files appear in the `output/` folder
3. Done

> **First launch note:** the first run will take a few minutes, as the tool automatically downloads and installs its dependencies (embedded Python ~10 MB, FFmpeg ~120 MB). Subsequent launches are instant.

## What it does

Discord requires videos to be under 10 MB and encoded in H.264 to play inline in a chat. This tool handles the conversion automatically, using the following strategy:

1. **Already compatible?** If the file is already H.264 MP4 and under 10 MB, it is copied as-is.
2. **Too heavy?** The target bitrate is calculated from the video duration to fit within 9.5 MB (with margin).
3. **Resolution is reduced first** — if the bitrate budget doesn't allow for the source resolution, the tool steps down through a quality ladder: 1080p → 720p → 480p → 360p.
4. **Quality is reduced last** — if the video is already at 720p or lower, only the bitrate is reduced to meet the size target.

Encoding uses a two-pass H.264 process for accurate size control.

## Supported formats

Any format supported by FFmpeg: MP4, MKV, AVI, MOV, WebM, and more.

## Requirements

- Windows only (for now)
- Internet connection on first launch (to download dependencies)

## Roadmap

- macOS / Linux support
- Custom size target (for Discord Nitro users with higher limits)
- Audio-only stripping option
- GUI / system tray integration
- Batch processing via folder watch
