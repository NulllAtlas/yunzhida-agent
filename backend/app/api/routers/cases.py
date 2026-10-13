"""主流程 API 路由（D1/D2/D7）：创建案件、查询状态、查询结果、统一提交入口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile

from app.api.tasks import task_manager
from app.core.config import settings
from app.core.db import insert_timeline, list_records
from app.core.errors import ApiError
from app.core.security import get_optional_user
from app.schemas.models import CaseInput, TaskInfo
from app.services.video_clip import extract_clip, probe_video, resolve_window

router = APIRouter(prefix="/api", tags=["cases"])

_VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv")
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

# 现场照片是补充证据，不是主证据：数量与体积都收着点，免得一次交上来几十张
_MAX_PHOTOS = 3
_MAX_PHOTO_MB = 10

# 自动取证（B1）：事故前默认回看 30 秒、事后保留 5 秒（"事故前几十秒"）
_FORENSICS_PRE_S = 30.0
_FORENSICS_POST_S = 5.0

# 任务在 TaskManager 内存里只活到进程结束；这两个状态之外的都是"还没跑完"
_TERMINAL = ("done", "failed")


def _owner_of(user: dict | None) -> str:
    """登录车主提交的案件绑定到账号（B2）；交警/匿名提交不绑定。"""
    if user and user.get("role") == "owner":
        return user["username"]
    return ""


def _resolve_media(video_id: str | None) -> str | None:
    """把 video_id 解析为上传目录内的媒体文件路径，文件存在才返回。

    不存在时返回 None，由感知服务走文字降级路径（保证链路不断）。
    """
    if not video_id:
        return None
    candidate = Path(video_id)
    if not candidate.is_absolute():
        candidate = Path(settings.upload_dir) / video_id
    return str(candidate) if candidate.is_file() else None


def _new_task(
    *,
    input_text: str,
    filename: str = "",
    media_path: str | None = None,
    photo_paths: list[str] | None = None,
    owner_id: str = "",
    flow_status: str = "submitted",
) -> TaskInfo:
    """建任务（先建任务再落盘文件：文件名里要带 task_id）。"""
    return task_manager.create(
        input_text=input_text,
        media_path=media_path,
        filename=filename,
        photo_paths=list(photo_paths or []),
        owner_id=owner_id,
        flow_status=flow_status,
    )


def _launch(
    background: BackgroundTasks,
    task: TaskInfo,
    *,
    run_text: str,
    media_path: str | None = None,
    photo_paths: list[str] | None = None,
) -> None:
    """把任务挂到后台执行（三个提交入口共用，保证行为一致）。"""
    background.add_task(
        task_manager.run, task, run_text, media_path, list(photo_paths or [])
    )


async def _save_upload(
    file: UploadFile,
    *,
    task_id: str,
    kind: str,
    exts: tuple[str, ...],
    max_mb: int,
    tag: str = "",
) -> str:
    """校验并落盘一个上传文件，返回落盘路径。

    命名：`{task_id}{tag}{suffix}`；违规（类型/大小）直接抛 ApiError 让前端看到原因，
    而不是悄悄吞掉文件让分析凭空少一份证据。
    """
    name = Path(file.filename or "").name
    lower = name.lower()
    content_type = file.content_type or ""
    is_media = content_type.startswith("image/" if kind == "照片" else "video/")
    if not (is_media or lower.endswith(exts)):
        raise ApiError(
            "INVALID_FILE",
            f"只接受{kind}文件（{'/'.join(e.lstrip('.') for e in exts)}）",
            422,
        )
    data = await file.read()
    if len(data) > max_mb * 1024 * 1024:
        raise ApiError("FILE_TOO_LARGE", f"{kind}超过 {max_mb}MB 上限", 422)

    suffix = Path(lower).suffix or exts[0]
    save_path = Path(settings.upload_dir) / f"{task_id}{tag}{suffix}"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(data)
    return str(save_path)


@router.post("/submissions", response_model=TaskInfo, status_code=202)
async def create_submission(
    background: BackgroundTasks,
    description: str = Form(""),
    video: UploadFile | None = File(None),
    photos: list[UploadFile] | None = File(None),
    user: dict | None = Depends(get_optional_user),
) -> TaskInfo:
    """统一提交入口：视频 / 文字描述 / 现场照片**任意组合**。

        - 视频：多帧检测+追踪（既有链路）；
        - 照片：单帧检测 → scene.photos，作为补充证据进判定上下文
          （静态画面没有速度/方向，不参与事故门控）；
        - 文字：用户补充描述，与场景证据同时进 prompt（不再二选一）。

    与 `/api/videos`、`/api/cases` 的区别是这三种输入可以在一次提交里一起给。
    """
    text = (description or "").strip()
    video_file = video if video is not None and video.filename else None
    photo_files = [f for f in (photos or []) if f is not None and f.filename]

    if not (text or video_file or photo_files):
        raise ApiError("EMPTY_INPUT", "请至少提供文字描述 / 视频 / 现场照片之一", 422)
    if len(photo_files) > _MAX_PHOTOS:
        raise ApiError("TOO_MANY_PHOTOS", f"现场照片最多 {_MAX_PHOTOS} 张", 422)

    # filename 只用来标记"这次带了视频"（记录列表的标题）：纯照片/文字提交留空，
    # 由前端按输入组合生成标题 —— 否则会把照片的落盘名当成原始文件名显示出来
    task = _new_task(
        input_text=text,
        filename=Path(video_file.filename).name if video_file is not None else "",
        owner_id=_owner_of(user),
    )

    media_path: str | None = None
    if video_file is not None:
        media_path = await _save_upload(
            video_file, task_id=task.task_id, kind="视频",
            exts=_VIDEO_EXTS, max_mb=settings.max_upload_mb,
        )

    photo_paths: list[str] = []
    for idx, photo in enumerate(photo_files):
        photo_paths.append(
            await _save_upload(
                photo, task_id=task.task_id, kind="照片",
                exts=_PHOTO_EXTS, max_mb=_MAX_PHOTO_MB, tag=f"_p{idx}",
            )
        )

    # 交给链路的是原始文字（不做兜底编造）：文字为空时场景证据就是唯一依据
    _launch(
        background, task,
        run_text=text, media_path=media_path, photo_paths=photo_paths,
    )
    return task


@router.post("/videos", response_model=TaskInfo, status_code=202)
async def upload_video(
    background: BackgroundTasks, file: UploadFile = File(...),
    user: dict | None = Depends(get_optional_user),
) -> TaskInfo:
    """接收行车记录仪视频：保存到上传目录并启动多智能体分析（异步，返回 task_id）。

    前端拿到 task_id 后轮询 /api/tasks/{id}/status，done 后 result 即完整分析结果。
    视频+文字/照片的组合提交请走 `POST /api/submissions`。
    """
    # 存原始文件名给车主端记录列表用（下面小写化的 name 只适合判扩展名）；
    # 走一次 Path().name 去掉浏览器可能带上的目录部分
    task = _new_task(
        input_text="", filename=Path(file.filename or "video.mp4").name or "video.mp4",
        owner_id=_owner_of(user),
    )
    save_path = await _save_upload(
        file, task_id=task.task_id, kind="视频",
        exts=_VIDEO_EXTS, max_mb=settings.max_upload_mb,
    )

    _launch(background, task, run_text="", media_path=save_path)
    return task


@router.post("/cases", response_model=TaskInfo, status_code=202)
async def create_case(
    case: CaseInput, background: BackgroundTasks,
    user: dict | None = Depends(get_optional_user),
) -> TaskInfo:
    """创建案件并启动多智能体分析（异步，立即返回 pending 状态）。"""
    text = (case.text_description or "").strip()
    if not (case.video_id or case.scene_id or text):
        raise ApiError(
            "EMPTY_INPUT",
            "请至少提供 video_id / scene_id / text_description 之一",
            422,
        )
    media_path = _resolve_media(case.video_id)
    task = _new_task(input_text=text, media_path=media_path, owner_id=_owner_of(user))
    _launch(
        background, task,
        run_text=text or "路口两车发生碰撞，疑似追尾", media_path=media_path,
    )
    return task


@router.post("/cases/forensics", response_model=TaskInfo, status_code=202)
async def forensics_trigger(
    background: BackgroundTasks,
    video: UploadFile = File(...),
    trigger_seconds: float | None = Form(None, ge=0),
    pre_seconds: float = Form(_FORENSICS_PRE_S, ge=0, le=300),
    post_seconds: float = Form(_FORENSICS_POST_S, ge=0, le=300),
    device_id: str = Form(""),
    description: str = Form(""),
    photos: list[UploadFile] | None = File(None),
    user: dict | None = Depends(get_optional_user),
) -> TaskInfo:
    """行车记录仪自动取证入口（B1）：事故触发时自动调取"事发前几十秒"片段并研判。

    与 `/api/videos`（车主手动上传完整录像）的区别：这里由设备在事故发生时触发，
    上传滚动录像 + 触发时刻，后端按触发点回退 `pre_seconds` 秒截出片段，
    只把这段**含事发前画面**的证据送进研判链路（手动上传常常只剩事故后画面）。
    截取失败时降级为使用原视频，链路不断。

    起始业务状态为 `forensics`（自动取证中，B4），研判完成后推进到"待交警受理"。
    """
    text = (description or "").strip()
    photo_files = [f for f in (photos or []) if f is not None and f.filename]
    if len(photo_files) > _MAX_PHOTOS:
        raise ApiError("TOO_MANY_PHOTOS", f"现场照片最多 {_MAX_PHOTOS} 张", 422)

    task = _new_task(
        input_text=text,
        filename=Path(video.filename or "dashcam.mp4").name,
        owner_id=_owner_of(user),
        flow_status="forensics",
    )

    # 原视频：设备上传的滚动录像全程先落盘，再从它裁出取证片段
    raw_path = await _save_upload(
        video, task_id=task.task_id, kind="视频",
        exts=_VIDEO_EXTS, max_mb=settings.max_upload_mb, tag="_raw",
    )

    duration, _fps, _frames, _size = probe_video(raw_path)
    start, end, trigger = resolve_window(
        trigger_s=trigger_seconds, duration=duration,
        pre_s=pre_seconds, post_s=post_seconds,
    )
    clip_path = str(Path(settings.upload_dir) / f"{task.task_id}_clip.mp4")
    clip = extract_clip(raw_path, clip_path, start_s=start, end_s=end)

    media_path = clip["path"] if clip["ok"] else raw_path
    if clip["ok"]:
        detail = (
            f"设备 {device_id or '未上报'} 自动触发取证：录像 {duration:.1f}s，触发时刻 {trigger:.1f}s，"
            f"截取事发前 {pre_seconds:g}s ~ 事后 {post_seconds:g}s"
            f"（{clip['start']}s~{clip['end']}s，{clip['duration']}s / {clip['frames']} 帧）"
        )
    else:
        detail = f"自动取证片段截取失败（{clip['error']}），已用原视频继续研判"
    insert_timeline(task.task_id, "forensics", "行车记录仪自动取证", detail)

    photo_paths: list[str] = []
    for idx, photo in enumerate(photo_files):
        photo_paths.append(
            await _save_upload(
                photo, task_id=task.task_id, kind="照片",
                exts=_PHOTO_EXTS, max_mb=_MAX_PHOTO_MB, tag=f"_p{idx}",
            )
        )

    _launch(
        background, task,
        run_text=text, media_path=media_path, photo_paths=photo_paths,
    )
    return task


@router.get("/tasks/{task_id}/status", response_model=TaskInfo)
async def get_status(task_id: str) -> TaskInfo:
    task = task_manager.get(task_id)
    if not task:
        raise ApiError("TASK_NOT_FOUND", "任务不存在", 404)
    return task


@router.get("/tasks/{task_id}/result", response_model=TaskInfo)
async def get_result(task_id: str) -> TaskInfo:
    task = task_manager.get(task_id)
    if not task:
        raise ApiError("TASK_NOT_FOUND", "任务不存在", 404)
    if task.status not in ("done", "failed"):
        raise ApiError("TASK_PROCESSING", "任务仍在处理中", 202)
    return task


def _history_item(record: dict) -> dict:
    """把库里一行整理成车主端记录列表项。

    顺手处理「上次进程死掉留下的半截任务」：任务状态平时活在 TaskManager 内存里，
    库里的 status 只在创建和结束时各写一次；进程重启后那些任务内存里已经没有对应
    对象、永远不会再推进了，不修正的话前端会一直转圈等一个不存在的结果。
    """
    status = record["status"]
    error = record.get("error")
    if status not in _TERMINAL and task_manager.get(record["task_id"]) is None:
        status = "failed"
        error = "后端重启，该次分析已中断（可重新提交）"

    return {
        "task_id": record["task_id"],
        "filename": record.get("filename") or "",
        "input_text": record.get("input_text") or "",
        "photos": record.get("photos") or [],
        "status": status,
        "flow_status": record.get("flow_status") or "submitted",
        "owner_id": record.get("owner_id") or "",
        "accident_type": record.get("accident_type"),
        "error": error,
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "result": record.get("result"),
    }


@router.get("/history")
async def history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict | None = Depends(get_optional_user),
) -> dict:
    """车主端「研判记录」：最近提交倒序，带完整研判结果。

    记录落在 SQLite（TaskManager 在创建/完成时各写一次），换浏览器、换设备
    看到的是同一份，不依赖 localStorage。

    登录车主只看自己名下的案件（B2 案件与车主绑定）；匿名/交警查看时不过滤
    （`POST /api/videos` 本身就允许匿名提交，车主端也没有强制账号）。
    """
    owner_id = _owner_of(user) or None
    return {
        "code": 0,
        "msg": "ok",
        "data": [
            _history_item(r)
            for r in list_records(limit=limit, offset=offset, owner_id=owner_id)
        ],
    }


@router.get("/metrics")
async def metrics() -> dict:
    """运行指标（D8）：任务计数与并发水位。"""
    return {
        "code": 0,
        "msg": "ok",
        "data": {**task_manager.metrics, "tasks_total": len(task_manager.list_task_ids())},
    }