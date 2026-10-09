"""行车记录仪片段截取（B1）：从整段录像里切出"事发前 N 秒 ~ 事后 M 秒"的取证片段。

"事故发生时自动调取事故前几十秒视频"落地为：设备上传滚动录像 + 事故触发时刻，
后端按触发时刻回退 pre_seconds 秒截取片段，只把这段证据送进研判链路，
替代车主手动上传（手动上传通常只有事故后的画面，恰好缺失定责最需要的"事发前"）。

只做帧区间复制，不做缩放/转码族参数调整；截取失败由调用方降级为使用原视频。
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def probe_video(path: str) -> tuple[float, float, int, int]:
    """读视频元信息：(时长秒, 帧率, 帧数, 宽)，不可读时全部返回 0。"""
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return 0.0, 0.0, 0, 0
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = frames / fps if fps > 0 and frames > 0 else 0.0
        return duration, fps, frames, width if width else height
    finally:
        cap.release()


def extract_clip(src: str, dst: str, *, start_s: float, end_s: float) -> dict:
    """把 src 的 [start_s, end_s) 区间另存为 dst（mp4）。

    返回片段元信息 dict：`{ok, start, end, duration, frames, path, error}`；
    截取失败（无法解码 / 区间为空 / 写不出文件）时 ok=False 并给出 error，
    由调用方决定是否降级为原视频。
    """
    import cv2

    meta = {
        "ok": False,
        "start": round(max(0.0, start_s), 2),
        "end": round(max(start_s, end_s), 2),
        "duration": 0.0,
        "frames": 0,
        "path": "",
        "error": "",
    }

    duration, fps, total_frames, _size = probe_video(src)
    if fps <= 0 or total_frames <= 0:
        meta["error"] = "视频不可解码，无法自动截取"
        return meta

    # 触发时刻可能超过视频末尾（例如未显式给触发点、默认取"视频结尾"），先夹到有效范围
    start_s = max(0.0, min(start_s, duration))
    end_s = max(start_s, min(end_s, duration))
    if end_s - start_s < 0.1:
        meta["error"] = "截取区间为空（触发点超出视频范围）"
        meta["start"], meta["end"] = round(start_s, 2), round(end_s, 2)
        return meta

    cap = cv2.VideoCapture(str(src))
    writer = None
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0:
            meta["error"] = "视频尺寸无效，无法自动截取"
            return meta

        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
        )
        if not writer.isOpened():
            meta["error"] = "片段写出器打开失败"
            return meta

        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_s * fps))
        end_frame = int(end_s * fps)
        written = 0
        while written < end_frame - int(start_s * fps):
            ok, frame = cap.read()
            if not ok:
                break
            writer.write(frame)
            written += 1

        if written == 0:
            meta["error"] = "区间内未读到任何帧"
            return meta

        meta.update(
            ok=True,
            start=round(start_s, 2),
            end=round(end_s, 2),
            duration=round(written / fps, 2),
            frames=written,
            path=str(dst),
        )
        return meta
    except Exception as exc:  # noqa: BLE001 — 截取是增强能力，异常交给调用方降级
        logger.exception("extract clip failed: %s", src)
        meta["error"] = f"截取异常：{exc}"
        return meta
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        # 半成品片段不能留在磁盘上被误当成有效证据
        if not meta["ok"] and Path(dst).exists():
            try:
                Path(dst).unlink()
            except OSError:
                pass


def resolve_window(
    *, trigger_s: float | None, duration: float, pre_s: float, post_s: float
) -> tuple[float, float, float]:
    """算出取证区间与触发时刻：(start, end, trigger)。

    `trigger_s` 为空时默认"事故刚刚发生"（触发点取录像末尾），
    这样只需回退 pre_s 秒即可覆盖事发前画面。
    """
    trigger = duration if trigger_s is None else max(0.0, min(trigger_s, duration or trigger_s))
    start = max(0.0, trigger - max(0.0, pre_s))
    end = min(duration, trigger + max(0.0, post_s)) if duration > 0 else trigger + max(0.0, post_s)
    return start, end, trigger