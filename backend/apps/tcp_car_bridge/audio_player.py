from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import threading
from pathlib import Path
from typing import List, Optional, Sequence


DEFAULT_AUDIO_FILES: Sequence[str] = (
    "/home/jetson/car_audio/alert.mp3",
    "/home/jetson/car_audio/前方有危险.MP3",
    "/home/jetson/car_audio/reverse.mp3",
    "/home/jetson/car_audio/scared.mp3",
    "/home/jetson/car_audio/light_show.wav",
    "/home/jetson/audio/light_show.wav",
    "/usr/share/sounds/alsa/Front_Center.wav",
)


class AudioPlayer:
    def __init__(
        self,
        command: Optional[str] = None,
        audio_file: Optional[str] = None,
        player: Optional[str] = None,
    ) -> None:
        self._command = (
            command if command is not None else os.getenv("TCP_CAR_AUDIO_COMMAND", "")
        )
        self._audio_file = (
            audio_file
            if audio_file is not None
            else os.getenv("TCP_CAR_AUDIO_FILE", "")
        )
        self._player = (
            player if player is not None else os.getenv("TCP_CAR_AUDIO_PLAYER", "")
        )
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def play(self, track_index: int = 0, volume_percent: int = 80) -> None:
        volume = max(0, min(100, volume_percent))
        command = self._build_command(track_index=track_index, volume_percent=volume)
        with self._lock:
            self._stop_locked()
            self._set_volume(volume)
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1.0)

    def _build_command(self, track_index: int, volume_percent: int) -> List[str]:
        if self._command.strip():
            return shlex.split(self._command)

        audio_file = self._resolve_audio_file(track_index)
        if audio_file is not None:
            return self._file_command(audio_file, volume_percent)

        speaker_test = shutil.which("speaker-test")
        if speaker_test is not None:
            return [speaker_test, "-t", "sine", "-f", "880", "-l", "1"]

        raise RuntimeError(
            "No audio command or file configured. Set TCP_CAR_AUDIO_FILE or TCP_CAR_AUDIO_COMMAND."
        )

    def _resolve_audio_file(self, track_index: int) -> Optional[Path]:
        candidates = []
        if 0 <= track_index < len(DEFAULT_AUDIO_FILES):
            candidates.append(DEFAULT_AUDIO_FILES[track_index])
        if self._audio_file.strip():
            candidates.append(self._audio_file)
        candidates.extend(DEFAULT_AUDIO_FILES)

        for candidate in candidates:
            path = Path(candidate).expanduser()
            if path.exists():
                return path
        return None

    def _file_command(self, audio_file: Path, volume_percent: int) -> List[str]:
        if self._player.strip():
            return [*shlex.split(self._player), str(audio_file)]

        suffix = audio_file.suffix.lower()
        if suffix == ".mp3":
            player = (
                shutil.which("mpg123")
                or shutil.which("mpv")
                or shutil.which("ffplay")
            )
            if player is not None:
                if Path(player).name == "ffplay":
                    return [
                        player,
                        "-nodisp",
                        "-autoexit",
                        "-loglevel",
                        "quiet",
                        "-af",
                        f"volume={volume_percent / 100.0}",
                        str(audio_file),
                    ]
                if Path(player).name == "mpv":
                    return [
                        player,
                        "--no-video",
                        "--really-quiet",
                        f"--volume={volume_percent}",
                        str(audio_file),
                    ]
                return [player, "-q", str(audio_file)]
        if suffix in {".wav", ".wave"}:
            player = shutil.which("aplay") or shutil.which("paplay")
            if player is not None:
                if Path(player).name == "aplay":
                    return [player, "-q", str(audio_file)]
                return [player, str(audio_file)]

        player = shutil.which("ffplay") or shutil.which("mpv") or shutil.which("aplay")
        if player is None:
            raise RuntimeError(f"No audio player found for {audio_file}")
        if Path(player).name == "ffplay":
            return [
                player,
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-af",
                f"volume={volume_percent / 100.0}",
                str(audio_file),
            ]
        if Path(player).name == "mpv":
            return [
                player,
                "--no-video",
                "--really-quiet",
                f"--volume={volume_percent}",
                str(audio_file),
            ]
        return [player, "-q", str(audio_file)]

    def _set_volume(self, volume_percent: int) -> None:
        amixer = shutil.which("amixer")
        if amixer is not None:
            subprocess.run(
                [amixer, "sset", "Master", f"{volume_percent}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return

        pactl = shutil.which("pactl")
        if pactl is not None:
            subprocess.run(
                [pactl, "set-sink-volume", "@DEFAULT_SINK@", f"{volume_percent}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
