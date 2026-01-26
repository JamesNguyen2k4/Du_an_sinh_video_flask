import os
import json
import tempfile
import time
from typing import List, Tuple, Optional

from pydub import AudioSegment
from TTS.api import TTS


XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def normalize_to_mono16k(input_path: str) -> str:
    """Normalize an input audio file to mono 16 kHz wav.

    Returns path to a temporary wav file.
    """
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1)
    audio = audio.set_frame_rate(16000)

    temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    temp_wav_path = temp_wav.name
    temp_wav.close()
    audio.export(temp_wav_path, format="wav")
    return temp_wav_path


def list_supported_languages() -> List[str]:
    """Return a curated list of ISO codes supported by XTTS-v2.

    Note: XTTS is multilingual; this list represents commonly used codes.
    """
    return [
        "ar", "cs", "da", "de", "en", "es", "fi", "fr", "hi", "hu",
        "it", "ja", "ko", "nl", "pl", "pt", "ru", "sv", "tr", "uk",
        "vi", "zh"
    ]


def create_cloned_voice(reference_mp3_path: str, voices_root: str = "./cloned_voices") -> Tuple[bool, str, Optional[str]]:
    """Create a cloned voice profile from a reference mp3.

    Returns (ok, display_name, error_message).
    Display name uses the file name (without extension).
    """
    if not reference_mp3_path or not os.path.isfile(reference_mp3_path):
        return False, "", "File tham chiếu không tồn tại"

    display_name = os.path.splitext(os.path.basename(reference_mp3_path))[0]
    voice_id = f"{int(time.time())}_{display_name}"
    voice_dir = os.path.join(voices_root, voice_id)
    ensure_dir(voice_dir)

    # Normalize and save reference wav; also keep original mp3 name for display
    norm_wav = normalize_to_mono16k(reference_mp3_path)
    ref_mp3_dst = os.path.join(voice_dir, "reference.mp3")
    AudioSegment.from_file(reference_mp3_path).export(ref_mp3_dst, format="mp3")

    ref_wav_dst = os.path.join(voice_dir, "reference_16k_mono.wav")
    AudioSegment.from_file(norm_wav).export(ref_wav_dst, format="wav")

    # Save config metadata
    cfg = {
        "display_name": display_name,
        "voice_id": voice_id,
        "reference_mp3": os.path.basename(ref_mp3_dst),
        "reference_wav": os.path.basename(ref_wav_dst),
        "sample_rate": 16000,
        "channels": 1,
    }
    with open(os.path.join(voice_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    try:
        os.unlink(norm_wav)
    except Exception:
        pass

    return True, display_name, None


class XTTSInference:
    """Thin wrapper for XTTS-v2 synthesis with reference speaker wav."""

    def __init__(self, device: Optional[str] = None):
        self.model_name = XTTS_MODEL_NAME
        self.tts = TTS(self.model_name)
        self.device = device

    def synthesize(self, text: str, language: str, reference_wav_path: str) -> str:
        out_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        out_path = out_wav.name
        out_wav.close()
        self.tts.tts_to_file(
            text=text,
            language=language,
            speaker_wav=reference_wav_path,
            file_path=out_path
        )
        return out_path


