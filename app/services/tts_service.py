# app/services/tts_service.py
import os
import asyncio
import tempfile
from dataclasses import dataclass
from typing import Optional

from gtts import gTTS

try:
    import edge_tts
except Exception:
    edge_tts = None

from app.config import get_config
from src.utils.xtts_clone import create_cloned_voice, list_supported_languages, XTTSInference


# Bản đồ Edge voices theo language/gender (giữ y nguyên logic của bạn)
EDGE_VOICE_BY_LANG_GENDER = {
    "vi": {"Nữ": "vi-VN-HoaiMyNeural",      "Nam": "vi-VN-NamMinhNeural"},
    "en": {"Nữ": "en-US-JennyNeural",       "Nam": "en-US-GuyNeural"},
    "zh": {"Nữ": "zh-CN-XiaoxiaoNeural",    "Nam": "zh-CN-YunxiNeural"},
    "ja": {"Nữ": "ja-JP-NanamiNeural",      "Nam": "ja-JP-KeitaNeural"},
    "ko": {"Nữ": "ko-KR-SunHiNeural",       "Nam": "ko-KR-InJoonNeural"},
    "fr": {"Nữ": "fr-FR-DeniseNeural",      "Nam": "fr-FR-HenriNeural"},
    "de": {"Nữ": "de-DE-KatjaNeural",       "Nam": "de-DE-ConradNeural"},
    "es": {"Nữ": "es-ES-ElviraNeural",      "Nam": "es-ES-AlvaroNeural"},
    "it": {"Nữ": "it-IT-ElsaNeural",        "Nam": "it-IT-IsmaelNeural"},
    "pt": {"Nữ": "pt-BR-FranciscaNeural",   "Nam": "pt-BR-AntonioNeural"},
}

def get_edge_voice(lang_code: str, gender_label: str) -> Optional[str]:
    try:
        return EDGE_VOICE_BY_LANG_GENDER.get(lang_code, {}).get(gender_label)
    except Exception:
        return None


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _tmp_audio_path(suffix: str) -> str:
    cfg = get_config()
    tmpdir = cfg.TTS_TMP_DIR
    _ensure_dir(tmpdir)
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=tmpdir)
    path = f.name
    f.close()
    return path


@dataclass
class TTSRequest:
    text: str
    language: str = "vi"              # nội dung
    gender: str = "Nữ"                # Edge voice selection
    preferred_voice: Optional[str] = None

    # Voice mode
    voice_mode: str = "builtin"       # "builtin" | "clone"
    cloned_voice_name: Optional[str] = None
    cloned_lang: Optional[str] = None # lang cho XTTS


class TTSService:
    """
    Flask-friendly service:
    - builtin: EdgeTTS (nếu có) -> fallback gTTS (mp3)
    - clone: XTTS-v2 (wav) -> fallback builtin
    """

    def __init__(self):
        self.cfg = get_config()
    def list_builtin_voices(self, lang: str, gender_label: str) -> list[dict]:
        """
        List Edge-TTS voices by language + gender.
        Return: [{ "id": shortName, "name": friendlyName }, ...]
        """
        if edge_tts is None:
            return []

        # Map UI "Nam/Nữ" -> Edge "Male/Female"
        gender_label = (gender_label or "").strip()
        want_gender = "Female" if gender_label == "Nữ" else "Male"

        lang = (lang or "vi").strip().lower()

        # prefix theo dropdown của bạn
        locale_prefix = {
            "vi": "vi-",
            "en": "en-",
            "zh": "zh-",
            "ja": "ja-",
            "ko": "ko-",
            "fr": "fr-",
            "de": "de-",
            "es": "es-",
            "it": "it-",
            "pt": "pt-",
        }.get(lang, f"{lang}-")

        try:
            async def _run():
                return await edge_tts.list_voices()

            # Flask sync context
            try:
                allv = asyncio.run(_run())
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    allv = loop.run_until_complete(_run())
                finally:
                    loop.close()

            out: list[dict] = []
            for v in allv or []:
                short_name = v.get("ShortName")
                friendly = v.get("FriendlyName") or short_name
                locale = (v.get("Locale") or "").lower()
                gender = v.get("Gender")

                if not short_name:
                    continue
                if not locale.startswith(locale_prefix):
                    continue
                if gender != want_gender:
                    continue

                out.append({"id": short_name, "name": friendly})

            out.sort(key=lambda x: (x.get("name") or x.get("id") or ""))
            return out

        except Exception as e:
            print("[EdgeTTS] list_voices failed:", repr(e))
            return []
    # ---------- Clone voice management ----------
    def list_cloned_voice_display_names(self) -> list[str]:
        root = self.cfg.CLONED_VOICES_DIR
        out: list[str] = []
        if not os.path.isdir(root):
            return out

        # giống logic _get_cloned_voice_options của bạn
        for voice_id in sorted(os.listdir(root)):
            vdir = os.path.join(root, voice_id)
            if not os.path.isdir(vdir):
                continue

            cfg_path = os.path.join(vdir, "config.json")
            if os.path.isfile(cfg_path):
                try:
                    import json
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    dn = data.get("display_name")
                    if dn:
                        out.append(dn)
                        continue
                except Exception:
                    pass

            for fn in os.listdir(vdir):
                if fn.lower().endswith(".mp3"):
                    out.append(os.path.splitext(fn)[0])
                    break
        return out

    def create_clone_from_mp3(self, reference_mp3_path: str) -> tuple[bool, str, Optional[str]]:
        """
        Tạo voice clone profile (lưu vào CLONED_VOICES_DIR).
        Return (ok, display_name, err)
        """
        root = self.cfg.CLONED_VOICES_DIR
        _ensure_dir(root)
        return create_cloned_voice(reference_mp3_path, voices_root=root)

    def find_reference_wav_by_display_name(self, display_name: str) -> Optional[str]:
        root = self.cfg.CLONED_VOICES_DIR
        if not os.path.isdir(root):
            return None
        try:
            import json
            for voice_id in os.listdir(root):
                vdir = os.path.join(root, voice_id)
                cfg_path = os.path.join(vdir, "config.json")
                if not os.path.isfile(cfg_path):
                    continue
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if cfg.get("display_name") == display_name:
                    wav_name = cfg.get("reference_wav")
                    if wav_name:
                        wav_path = os.path.join(vdir, wav_name)
                        return wav_path if os.path.isfile(wav_path) else None
        except Exception:
            return None
        return None

    # ---------- Synthesis ----------
    def synthesize(self, req: TTSRequest) -> Optional[str]:
        """
        Trả về path audio:
        - builtin: .mp3
        - clone: .wav
        """
        text = (req.text or "").strip()
        if not text:
            return None

        language = (req.language or "vi").strip()
        gender = (req.gender or "Nữ").strip()

        if req.voice_mode == "clone" and req.cloned_voice_name:
            # XTTS synth
            ref_wav = self.find_reference_wav_by_display_name(req.cloned_voice_name)
            if ref_wav:
                try:
                    xtts = XTTSInference()
                    lang_code = (req.cloned_lang or language).strip()
                    # XTTS trả ra wav
                    return xtts.synthesize(text, lang_code, ref_wav)
                except Exception as e:
                    import traceback
                    print("[XTTS] synth failed:")
                    traceback.print_exc()

        # builtin path
        return self._builtin_tts_to_mp3(
            text=text,
            language=language,
            gender=gender,
            preferred_voice=req.preferred_voice,
        )

    def _builtin_tts_to_mp3(self, text: str, language: str, gender: str, preferred_voice: Optional[str]) -> Optional[str]:
        out_path = _tmp_audio_path(".mp3")
        voice = preferred_voice or get_edge_voice(language, gender)

        if edge_tts is not None and voice:
            try:
                async def _save():
                    communicate = edge_tts.Communicate(
                        text=text,
                        voice=voice,
                        rate="+0%",
                        volume="+0%"
                    )
                    await communicate.save(out_path)

                # asyncio.run sẽ lỗi nếu đang chạy trong event loop.
                # Flask thường không có loop sẵn, nhưng để an toàn:
                try:
                    asyncio.run(_save())
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(_save())
                    finally:
                        loop.close()

                return out_path
            except Exception as e:
                print("[EdgeTTS] failed:", repr(e))

        # fallback gTTS
        try:
            tts = gTTS(text=text, lang=language, slow=False)
            tts.save(out_path)
            return out_path
        except Exception as e:
            print("[gTTS] failed:", repr(e))
            return None
