# app/services/lecture_service.py
import os
import re
import gc
import time
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
from app.services.sadtalker_service import SadTalkerService, SadTalkerParams
import torch
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip

from app.config import get_config
from app.services.pptx_service import extract_slides_from_pptx
from app.services.tts_service import TTSService, TTSRequest


# ---------------- Utilities ----------------
def cleanup_cuda_memory():
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        gc.collect()
        print("🧹 CUDA memory cleaned up")
    except Exception as e:
        print(f"⚠️ CUDA cleanup warning: {str(e)}")


def check_system_memory() -> float:
    try:
        import psutil
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024**3)
        print(f"💾 Available RAM: {available_gb:.1f}GB")
        return available_gb
    except Exception:
        return 8.0


def get_audio_duration(audio_path: str) -> float:
    try:
        if audio_path and os.path.exists(audio_path):
            clip = AudioFileClip(audio_path)
            d = float(clip.duration)
            clip.close()
            return d
        return 0.0
    except Exception as e:
        print(f"Error getting audio duration: {str(e)}")
        return 0.0


def parse_user_slides_text(user_text: str) -> list[dict]:
    """
    Parse markdown/text:
      ## Slide 1
      Slide 1:
    """
    slides: list[dict] = []
    if not user_text or not user_text.strip():
        return slides

    txt = user_text.replace("\r\n", "\n")
    pattern = re.compile(r'(?im)^\s*(?:#+\s*)?slide\s+(\d+)\s*:?\s*$', re.MULTILINE)
    matches = list(pattern.finditer(txt))

    if not matches:
        return [{"slide_number": 1, "text": txt.strip(), "image_path": None, "has_math_objects": False}]

    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(txt)
        num = int(m.group(1))
        body = txt[start:end].strip()
        slides.append({"slide_number": num, "text": body, "image_path": None, "has_math_objects": False})

    slides.sort(key=lambda s: s["slide_number"])
    return slides


def merge_user_text_with_ppt_images(user_slides: list[dict], ppt_slides: list[dict]) -> list[dict]:
    """
    Gộp text do user sửa với ảnh gốc từ PPT.
    """
    if not user_slides:
        return ppt_slides or []
    if not ppt_slides:
        return user_slides

    by_num = {s.get("slide_number"): s for s in ppt_slides if s.get("slide_number") is not None}

    result: list[dict] = []
    for idx, us in enumerate(user_slides):
        img_path = None
        if us.get("slide_number") in by_num:
            img_path = by_num[us["slide_number"]].get("image_path")
        if img_path is None and idx < len(ppt_slides):
            img_path = ppt_slides[idx].get("image_path")

        result.append({
            "slide_number": us.get("slide_number", idx + 1),
            "text": us.get("text", ""),
            "image_path": img_path,
            "has_math_objects": False
        })
    return result


def create_slide_image_with_text(text: str, output_path: str, width: int = 1280, height: int = 720) -> Optional[str]:
    """
    Fallback nếu không có ảnh slide.
    """
    cfg = get_config()
    try:
        img = Image.new("RGB", (width, height), color="white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(cfg.FONT_PATH, 40)
        except Exception:
            font = ImageFont.load_default()

        text_lines = (text or "").split("\n")
        y_position = height // 2 - (len(text_lines) * 50) // 2

        for line in text_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x_position = (width - text_width) // 2
            draw.text((x_position, y_position), line, fill="black", font=font)
            y_position += text_height + 20

        img.save(output_path)
        return output_path
    except Exception as e:
        print(f"Error creating slide image: {str(e)}")
        return None


def _ensure_even_image(path: str) -> None:
    im = Image.open(path)
    w, h = im.size
    new_w = w + (w & 1)
    new_h = h + (h & 1)
    if new_w != w or new_h != h:
        bg = Image.new(im.mode, (new_w, new_h), (255, 255, 255))
        bg.paste(im, (0, 0))
        bg.save(path)


def pip_composite_ffmpeg(slide_png: str, teacher_mp4: str, out_mp4: str,
                         pip_ratio: float, margin: int, fps: int,
                         prefer_nvenc: bool = True) -> None:
    cfg = get_config()
    ffmpeg = cfg.FFMPEG_PATH

    if shutil.which(ffmpeg) is None:
        raise RuntimeError(f"ffmpeg không có trong PATH hoặc FFMPEG_PATH sai: {ffmpeg}")

    _ensure_even_image(slide_png)

    with Image.open(slide_png) as im:
        slide_w, _ = im.size
    teacher_target_w = max(1, int(slide_w * pip_ratio))

    vcodec = "h264_nvenc" if prefer_nvenc else "libx264"
    preset = "p5" if vcodec == "h264_nvenc" else "ultrafast"

    filter_complex = (
        "[0:v]pad=ceil(iw/2)*2:ceil(ih/2)*2[bg];"
        f"[1:v]scale={teacher_target_w}:-2:flags=lanczos[face];"
        f"[bg][face]overlay=W-w-{margin}:{margin},format=yuv420p[vout]"
    )

    cmd = [
        ffmpeg, "-y",
        "-loop", "1", "-i", slide_png,
        "-i", teacher_mp4,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "1:a?",
        "-c:v", vcodec,
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-shortest",
        "-c:a", "copy",
        out_mp4
    ]

    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        if vcodec == "h264_nvenc":
            # fallback libx264
            return pip_composite_ffmpeg(slide_png, teacher_mp4, out_mp4, pip_ratio, margin, fps, prefer_nvenc=False)
        err = p.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"ffmpeg overlay failed: {err}")


def adjust_audio_speed(in_path: str, rate: float) -> str:
    """
    ffmpeg atempo chain.
    """
    cfg = get_config()
    ffmpeg = cfg.FFMPEG_PATH

    try:
        if not in_path or not os.path.exists(in_path) or abs(rate - 1.0) < 1e-3:
            return in_path

        base, ext = os.path.splitext(in_path)
        out_path = f"{base}_r{rate:.2f}{ext or '.wav'}"

        r = float(rate)
        filters = []
        while r > 2.0 + 1e-9:
            filters.append("atempo=2.0")
            r /= 2.0
        while r < 0.5 - 1e-9:
            filters.append("atempo=0.5")
            r /= 0.5
        filters.append(f"atempo={r:.3f}")
        atempo_chain = ",".join(filters)

        cmd = [ffmpeg, "-y", "-i", in_path, "-filter:a", atempo_chain, out_path]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            err = p.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg atempo failed: {err}")

        return out_path if os.path.exists(out_path) else in_path
    except Exception as e:
        print(f"⚠️ adjust_audio_speed warning: {e}")
        return in_path


# ---------------- Main pipeline ----------------
@dataclass
class LectureParams:
    language: str = "vi"

    # voice
    voice_mode: str = "builtin"                 # "builtin" | "clone"
    gender: str = "Nữ"
    builtin_voice: Optional[str] = None
    cloned_voice_name: Optional[str] = None
    cloned_lang: Optional[str] = None

    # SadTalker params
    preprocess_type: str = "crop"
    is_still_mode: bool = False
    enhancer: bool = False
    batch_size: int = 2
    size_of_image: int = 256
    pose_style: int = 0

    # speed
    speech_rate: float = 1.0


def generate_teacher_video(
    sad_talker,
    source_image_path: str,
    text: str,
    params: LectureParams,
    tts_service: TTSService,
    pre_synth_audio_path: Optional[str] = None
) -> Optional[str]:
    """
    Sinh video teacher từ audio đã có hoặc synth bằng TTSService.
    """
    max_retries = 3
    retry_count = 0
    batch_size = params.batch_size

    while retry_count < max_retries:
        try:
            cleanup_cuda_memory()

            if not source_image_path or not os.path.exists(source_image_path):
                print(f"Source image not found: {source_image_path}")
                return None

            audio_path = pre_synth_audio_path
            if not audio_path:
                audio_path = tts_service.synthesize(TTSRequest(
                    text=text,
                    language=params.language,
                    gender=params.gender,
                    preferred_voice=params.builtin_voice,
                    voice_mode=params.voice_mode,
                    cloned_voice_name=params.cloned_voice_name,
                    cloned_lang=params.cloned_lang,
                ))
            if not audio_path:
                return None

            audio_path = adjust_audio_speed(audio_path, params.speech_rate)

            video_path = sad_service.generate(
                job_id=job_id or "nojob",
                source_image_path=source_image_path,
                audio_path=audio_path,
                params=SadTalkerParams(
                    preprocess_type=params.preprocess_type,
                    is_still_mode=params.is_still_mode,
                    enhancer=params.enhancer,
                    batch_size=batch_size,
                    size_of_image=params.size_of_image,
                    pose_style=params.pose_style,
                    exp_scale=1.0,
                )
            )

            # cleanup audio nếu tự synth trong hàm này
            if (pre_synth_audio_path is None) and audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

            if video_path and os.path.exists(video_path):
                cleanup_cuda_memory()
                return video_path
            return None

        except RuntimeError as e:
            if "CUDA out of memory" in str(e):
                retry_count += 1
                batch_size = max(1, batch_size // 2)
                cleanup_cuda_memory()
                time.sleep(2)
                continue
            print("Runtime error:", e)
            return None
        except Exception as e:
            print("Error generate_teacher_video:", e)
            return None

    return None


def create_lecture_video(
    sad_talker,
    slides_data: list[dict],
    source_image_path: str,
    params: LectureParams,
    job_id: Optional[str] = None,
    progress_cb=None,  # callable(slide_index:int, total:int, message:str)
) -> tuple[Optional[str], str]:
    """
    Core: tạo lecture_final.mp4
    """
    cfg = get_config()
    tts_service = TTSService()

    if not slides_data:
        return None, "❌ Không có slide nào để xử lý!"

    # output dir theo job_id (nếu có)
    folder_name = job_id or f"lecture_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir = os.path.join(cfg.RESULTS_DIR, folder_name)
    os.makedirs(output_dir, exist_ok=True)

    if check_system_memory() < 2.0:
        print("⚠️ Low RAM")

    safe_image_path = os.path.join(output_dir, "source_image.png")
    if not source_image_path or not os.path.exists(source_image_path):
        return None, "❌ Không tìm thấy ảnh nguồn!"
    shutil.copy2(source_image_path, safe_image_path)

    total_duration = 0.0
    temp_teacher_videos: list[str] = []
    final_piece_files: list[str] = []

    for i, slide_data in enumerate(slides_data):
        if progress_cb:
            progress_cb(i + 1, len(slides_data), f"Processing slide {i+1}/{len(slides_data)}")

        slide_png = os.path.join(output_dir, f"slide_{i+1:02d}.png")
        original_image = slide_data.get("image_path")

        if original_image and os.path.exists(original_image):
            try:
                shutil.copy2(original_image, slide_png)
            except Exception:
                if not create_slide_image_with_text(slide_data.get("text", ""), slide_png):
                    continue
        else:
            if not create_slide_image_with_text(slide_data.get("text", ""), slide_png):
                continue

        # 1) synth audio 1 lần cho slide
        audio_path = tts_service.synthesize(TTSRequest(
            text=slide_data.get("text", ""),
            language=params.language,
            gender=params.gender,
            preferred_voice=params.builtin_voice,
            voice_mode=params.voice_mode,
            cloned_voice_name=params.cloned_voice_name,
            cloned_lang=params.cloned_lang,
        ))
        if not audio_path:
            # silent fallback
            try:
                from pydub import AudioSegment
                silent_wav = os.path.join(output_dir, f"silent_{i+1:02d}.wav")
                AudioSegment.silent(duration=3000).export(silent_wav, format="wav")
                audio_path = silent_wav
            except Exception:
                continue

        audio_path = adjust_audio_speed(audio_path, params.speech_rate)
        audio_duration = get_audio_duration(audio_path)
        if audio_duration <= 0.1:
            audio_duration = 3.0

        # 2) generate teacher video using pre_synth_audio
        teacher_video_path = generate_teacher_video(
            sad_talker=sad_talker,
            source_image_path=safe_image_path,
            text=slide_data.get("text", ""),
            params=params,
            tts_service=tts_service,
            pre_synth_audio_path=audio_path
        )
        cleanup_cuda_memory()

        if not teacher_video_path or not os.path.exists(teacher_video_path):
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
            except Exception:
                pass
            continue

        # 3) overlay PIP
        slide_mp4 = os.path.abspath(os.path.join(output_dir, f"slide_{i+1:03d}.mp4"))
        try:
            pip_composite_ffmpeg(
                slide_png=slide_png,
                teacher_mp4=teacher_video_path,
                out_mp4=slide_mp4,
                pip_ratio=cfg.PIP_RATIO,
                margin=cfg.PIP_MARGIN,
                fps=cfg.PIP_FPS,
                prefer_nvenc=True
            )
        except Exception as e:
            print("overlay failed:", e)
            continue

        final_piece_files.append(slide_mp4)
        temp_teacher_videos.append(teacher_video_path)
        total_duration += audio_duration

        # cleanup temp
        time.sleep(0.2)
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass
        try:
            if os.path.exists(slide_png):
                os.remove(slide_png)
        except Exception:
            pass

    if not final_piece_files:
        return None, "❌ Không thể tạo video cho bất kỳ slide nào!"

    final_video_path = os.path.join(output_dir, "lecture_final.mp4")

    # concat fast
    concat_list = os.path.join(output_dir, "concat_list.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in final_piece_files:
            ap = os.path.abspath(p).replace("'", r"'\''")
            f.write(f"file '{ap}'\n")

    ffmpeg = cfg.FFMPEG_PATH
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", final_video_path]
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        print("ffmpeg concat failed, fallback moviepy:", e)
        try:
            reopened = [VideoFileClip(p) for p in final_piece_files]
            final_clip = concatenate_videoclips(reopened, method="chain")
            final_clip.write_videofile(
                final_video_path,
                codec="libx264",
                audio_codec="aac",
                verbose=False,
                logger=None,
                preset="ultrafast",
                ffmpeg_params=["-crf", "23"]
            )
            for rc in reopened:
                try:
                    rc.close()
                except Exception:
                    pass
        except Exception as concat_fallback_error:
            return None, f"❌ Failed to concatenate video clips: {concat_fallback_error}"

    # cleanup concat list
    try:
        os.remove(concat_list)
    except Exception:
        pass

    # cleanup teacher videos
    for v in temp_teacher_videos:
        try:
            if os.path.exists(v):
                os.remove(v)
        except Exception:
            pass

    # cleanup temp SadTalker dirs (uuid-like) — bạn có thể để, hoặc làm scheduled cleanup
    try:
        results_dir = cfg.RESULTS_DIR
        for item in os.listdir(results_dir):
            p = os.path.join(results_dir, item)
            if os.path.isdir(p) and len(item) == 36 and "-" in item:
                try:
                    shutil.rmtree(p)
                except Exception:
                    pass
    except Exception:
        pass

    cleanup_cuda_memory()
    status_text = f"✅ Hoàn thành! {len(slides_data)} slide, tổng thời gian ước tính: {total_duration:.1f}s"
    return final_video_path, status_text


def build_lecture_from_inputs(
    sad_talker,
    pptx_path: Optional[str],
    source_image_path: str,
    params: LectureParams,
    user_slides_text: Optional[str] = None,
    job_id: Optional[str] = None,
    progress_cb=None,
) -> tuple[Optional[str], str]:
    """
    Thay cho generate_lecture_video_handler (Gradio).
    """
    user_slides = parse_user_slides_text(user_slides_text or "")

    ppt_slides = []
    if pptx_path:
        ppt_slides = extract_slides_from_pptx(pptx_path)

    if user_slides:
        slides_data = merge_user_text_with_ppt_images(user_slides, ppt_slides)
    else:
        if not ppt_slides:
            return None, "❌ Vui lòng chọn PowerPoint hoặc nhập nội dung slide!"
        slides_data = ppt_slides

    if not source_image_path:
        return None, "❌ Vui lòng chọn ảnh giáo viên!"
    if not slides_data:
        return None, "❌ Không có slide nào để xử lý!"

    return create_lecture_video(
        sad_talker=sad_talker,
        slides_data=slides_data,
        source_image_path=source_image_path,
        params=params,
        job_id=job_id,
        progress_cb=progress_cb
    )
