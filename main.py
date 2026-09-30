from __future__ import annotations

import asyncio
import io
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
app = FastAPI(title="多平台学习进度监测助手", version="2.2.0")

# Production CORS: set FRONTEND_ORIGINS to a comma-separated allowlist.
# Example: https://learning.example.com,https://www.learning.example.com
_cors_origins = [item.strip() for item in os.getenv("FRONTEND_ORIGINS", "*").split(",") if item.strip()]
_cors_wildcard = _cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=not _cors_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_DATA: list[dict[str, Any]] = [
    {"name": "林晓雨", "student_id": "2024001", "class_name": "计科 2401", "rain_classroom": 92, "head_course": 88, "mooc_score": 91, "chaoxing_score": 87, "last_active": "2025-05-16", "course": "Python 程序设计"},
    {"name": "陈子墨", "student_id": "2024002", "class_name": "计科 2401", "rain_classroom": 76, "head_course": 68, "mooc_score": 72, "chaoxing_score": 70, "last_active": "2025-05-15", "course": "Python 程序设计"},
    {"name": "周可欣", "student_id": "2024003", "class_name": "计科 2401", "rain_classroom": 58, "head_course": 46, "mooc_score": 55, "chaoxing_score": 61, "last_active": "2025-05-12", "course": "数据结构"},
    {"name": "王浩然", "student_id": "2024004", "class_name": "计科 2401", "rain_classroom": 34, "head_course": 28, "mooc_score": 31, "chaoxing_score": 36, "last_active": "2025-05-08", "course": "数据结构"},
    {"name": "赵一诺", "student_id": "2024005", "class_name": "计科 2402", "rain_classroom": 81, "head_course": 74, "mooc_score": 84, "chaoxing_score": 78, "last_active": "2025-05-16", "course": "Web 前端开发"},
    {"name": "黄嘉乐", "student_id": "2024006", "class_name": "计科 2402", "rain_classroom": 43, "head_course": 55, "mooc_score": 49, "chaoxing_score": 52, "last_active": "2025-05-13", "course": "Web 前端开发"},
    {"name": "杨书涵", "student_id": "2024007", "class_name": "计科 2402", "rain_classroom": 97, "head_course": 93, "mooc_score": 95, "chaoxing_score": 94, "last_active": "2025-05-17", "course": "Python 程序设计"},
    {"name": "刘宇轩", "student_id": "2024008", "class_name": "计科 2402", "rain_classroom": 63, "head_course": 61, "mooc_score": 67, "chaoxing_score": 64, "last_active": "2025-05-14", "course": "数据结构"},
    {"name": "孙梦琪", "student_id": "2024009", "class_name": "计科 2403", "rain_classroom": 27, "head_course": 39, "mooc_score": 42, "chaoxing_score": 35, "last_active": "2025-05-06", "course": "Web 前端开发"},
    {"name": "吴俊驰", "student_id": "2024010", "class_name": "计科 2403", "rain_classroom": 72, "head_course": 82, "mooc_score": 75, "chaoxing_score": 80, "last_active": "2025-05-15", "course": "Python 程序设计"},
    {"name": "徐安琪", "student_id": "2024011", "class_name": "计科 2403", "rain_classroom": 49, "head_course": 36, "mooc_score": 45, "chaoxing_score": 40, "last_active": "2025-05-11", "course": "数据结构"},
    {"name": "郭明哲", "student_id": "2024012", "class_name": "计科 2403", "rain_classroom": 85, "head_course": 79, "mooc_score": 88, "chaoxing_score": 83, "last_active": "2025-05-16", "course": "Web 前端开发"},
]

FIELD_ALIASES = {
    "name": {"name", "姓名", "学生姓名", "student", "studentname"},
    "student_id": {"student_id", "学号", "学生学号", "id", "studentid", "用户id"},
    "class_name": {"class_name", "班级", "行政班", "class"},
    "rain_classroom": {"rain_classroom", "雨课堂", "雨课堂观看率", "观看进度", "视频观看率", "观看率", "rain", "rainrate"},
    "head_course": {"head_course", "头歌", "头歌完成率", "实验完成率", "实训完成率", "实验进度", "head", "headrate"},
    "mooc_score": {"mooc", "中国大学mooc", "中国大学_mooc", "mooc成绩", "mooc完成率", "课程完成率"},
    "chaoxing_score": {"chaoxing", "学习通", "学习通成绩", "作业得分", "作业完成率", "超星"},
    "last_active": {"last_active", "最近学习", "最近活跃", "最后学习时间", "lastactive"},
    "course": {"course", "课程", "课程名称"},
}
PLATFORM_ALIASES = {"rain": {"rain", "雨课堂", "yuketang"}, "head": {"head", "头歌", "hippo"}, "mooc": {"mooc", "中国大学mooc", "中国大学_mooc"}, "chaoxing": {"chaoxing", "学习通", "超星"}}
CURRENT_DATA: list[dict[str, Any]] = SAMPLE_DATA
RAG_CHUNKS: list[dict[str, str]] = []
RAG_DOCS: list[str] = []


def _key(value: Any) -> str:
    return re.sub(r"[\s_\-（）()]+", "", str(value).strip().lower())


def _find_columns(frame: pd.DataFrame) -> dict[str, Any]:
    mapped = {}
    aliases = {_key(alias): field for field, values in FIELD_ALIASES.items() for alias in values}
    for column in frame.columns:
        normalized = _key(column)
        if normalized in aliases:
            mapped[aliases[normalized]] = column
    return mapped


def _number(raw: Any) -> float:
    if raw is None or pd.isna(raw):
        return 0.0
    text = str(raw).strip().replace(",", "").replace("%", "")
    if not text:
        return 0.0
    number = float(text)
    return round(max(0, min(100, number * 100 if 0 < number <= 1 else number)), 1)


def _read_frame(filename: str, content: bytes) -> pd.DataFrame:
    if filename.endswith(".csv"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(content), encoding="gbk")
    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content))
    raise HTTPException(status_code=415, detail="仅支持 CSV、XLSX 或 XLS 文件")


def _normalize_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    mapped = _find_columns(frame)
    if "name" not in mapped and "student_id" not in mapped:
        raise ValueError("文件至少需要包含“姓名”或“学号”列")
    result = []
    for index, row in frame.iterrows():
        def value(field: str, fallback: Any = "") -> Any:
            column = mapped.get(field)
            if column is None or pd.isna(row[column]):
                return fallback
            return row[column]
        name = str(value("name", "未命名学生")).strip()
        student_id = str(value("student_id", f"S{index + 1:04d}")).replace(".0", "").strip()
        if name == "未命名学生" and student_id.startswith("S"):
            continue
        result.append({"name": name, "student_id": student_id, "class_name": str(value("class_name", "未分班")), "rain_classroom": _number(value("rain_classroom")), "head_course": _number(value("head_course")), "mooc_score": _number(value("mooc_score")), "chaoxing_score": _number(value("chaoxing_score")), "last_active": str(value("last_active", "-")), "course": str(value("course", "未指定课程"))})
    if not result:
        raise ValueError("文件中没有可用的学生记录")
    return result


def _platform_from_filename(filename: str) -> str:
    lower = filename.lower()
    for platform, aliases in PLATFORM_ALIASES.items():
        if any(alias.lower() in lower for alias in aliases):
            return platform
    return "unknown"


def _merge_platform_files(items: list[tuple[str, bytes]]) -> tuple[list[dict[str, Any]], list[str]]:
    merged: dict[str, dict[str, Any]] = {}
    messages = []
    for filename, content in items:
        platform = _platform_from_filename(filename)
        frame = _read_frame(filename.lower(), content)
        mapped = _find_columns(frame)
        if "student_id" not in mapped:
            raise ValueError(f"{filename} 缺少学号列，无法安全关联")
        count = 0
        for index, row in frame.iterrows():
            student_id = str(row[mapped["student_id"]]).replace(".0", "").strip()
            if not student_id or student_id == "nan":
                continue
            record = merged.setdefault(student_id, {"student_id": student_id, "name": "", "class_name": "未分班", "course": "未指定课程", "last_active": "-", "rain_classroom": 0.0, "head_course": 0.0, "mooc_score": 0.0, "chaoxing_score": 0.0})
            for field in ("name", "class_name", "course", "last_active"):
                if field in mapped and str(row[mapped[field]]) not in ("", "nan", "NaT"):
                    record[field] = str(row[mapped[field]])
            target = {"rain": "rain_classroom", "head": "head_course", "mooc": "mooc_score", "chaoxing": "chaoxing_score"}.get(platform)
            if target and target in mapped:
                record[target] = _number(row[mapped[target]])
            else:
                for field in ("rain_classroom", "head_course", "mooc_score", "chaoxing_score"):
                    if field in mapped:
                        record[field] = _number(row[mapped[field]])
            count += 1
        messages.append(f"{filename}: 识别为 {platform}，合并 {count} 条")
    result = list(merged.values())
    if not result:
        raise ValueError("没有找到可按学号合并的记录")
    return result, messages


app.mount("/static", StaticFiles(directory=TEMPLATE_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    page = TEMPLATE_DIR / "index.html"
    if not page.is_file():
        raise HTTPException(status_code=500, detail="找不到 templates/index.html")
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "learning-progress-monitor"}


@app.get("/api/data")
async def get_data() -> dict[str, Any]:
    return {"students": SAMPLE_DATA, "source": "sample", "count": len(SAMPLE_DATA)}


@app.post("/api/data")
async def upload_data(file: UploadFile = File(...)) -> dict[str, Any]:
    global CURRENT_DATA
    try:
        students = _normalize_frame(_read_frame((file.filename or "").lower(), await file.read()))
        CURRENT_DATA = students
        return {"students": students, "source": "upload", "count": len(students), "filename": file.filename}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"无法解析数据文件：{exc}") from exc


@app.post("/api/upload-multi")
async def upload_multi(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    global CURRENT_DATA
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个平台文件")
    try:
        items = [((file.filename or "未命名文件").lower(), await file.read()) for file in files]
        students, messages = _merge_platform_files(items)
        CURRENT_DATA = students
        return {"students": students, "source": "multi-platform", "count": len(students), "platforms": messages, "merged_by": "student_id"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"多平台合并失败：{exc}") from exc


class AITextRequest(BaseModel):
    student_name: str = Field(default="同学", max_length=100)
    course: str = Field(default="当前课程", max_length=200)
    rain_classroom: float = Field(default=0, ge=0, le=100)
    head_course: float = Field(default=0, ge=0, le=100)
    tone: str = Field(default="友好", max_length=30)
    api_key: str | None = Field(default=None, max_length=300)
    base_url: str | None = Field(default=None, max_length=500)


def _fallback_message(payload: AITextRequest) -> str:
    weakest = "雨课堂观看进度" if payload.rain_classroom < payload.head_course else "头歌实训完成进度"
    return f"{payload.student_name}同学，你好！关注到你在《{payload.course}》的学习进度还可以再提升一下：雨课堂观看率为 {payload.rain_classroom:.0f}%，头歌完成率为 {payload.head_course:.0f}%。建议你本周优先补齐{weakest}，每天安排一段专注学习时间，遇到困难及时联系老师。期待看到你的进步！"


def _deepseek_base_url() -> str:
    """Allow a local proxy or OpenAI-compatible gateway without changing frontend code."""
    value = (os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")).strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = "https://api.deepseek.com/v1"
    return value


def _network_hint(exc: Exception) -> str:
    message = str(exc).lower()
    if any(word in message for word in ("connect", "timeout", "proxy", "name or service", "network", "dns")):
        return "网络无法连接 DeepSeek；请配置 HTTPS_PROXY/ALL_PROXY，或设置 DEEPSEEK_BASE_URL 为可访问的兼容网关"
    if "401" in message or "authentication" in message or "api key" in message:
        return "DeepSeek API Key 无效或未授权"
    if "429" in message or "rate limit" in message:
        return "DeepSeek 请求频率受限，请稍后重试"
    return f"DeepSeek 请求失败（{type(exc).__name__}）"


async def _deepseek(prompt: str, api_key: str | None = None, base_url: str | None = None) -> tuple[str | None, str | None]:
    key = (api_key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
    if not key:
        return None, "未配置 DEEPSEEK_API_KEY"
    # OpenAI SDK/httpx honors HTTPS_PROXY, HTTP_PROXY and ALL_PROXY from the process environment.
    client = OpenAI(api_key=key, base_url=(base_url or _deepseek_base_url()), timeout=60.0, max_retries=0)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            )
            text = (response.choices[0].message.content or "").strip()
            if text:
                return text, None
            raise ValueError("AI 返回内容为空")
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                await asyncio.sleep(1.0 * (attempt + 1))
    return None, _network_hint(last_error) if last_error else "DeepSeek 未返回内容"


@app.post("/api/generate-ai-text")
async def generate_ai_text(payload: AITextRequest) -> dict[str, Any]:
    prompt = f"请用{payload.tone}、尊重且具体的语气，写一段给学生的中文学习督促消息，约100字。学生：{payload.student_name}；课程：{payload.course}；雨课堂观看率：{payload.rain_classroom:.0f}%；头歌完成率：{payload.head_course:.0f}%。避免指责，给出可执行建议。只输出消息正文。"
    text, error = await _deepseek(prompt, payload.api_key, payload.base_url)
    if text:
        return {"text": text, "warning": False, "source": "deepseek", "message": None}
    return {"text": _fallback_message(payload), "warning": True, "source": "template", "message": f"{error}，已使用本地模板"}



@app.post("/api/rag/upload-doc")
async def rag_upload_doc(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = (file.filename or "").lower()
    content = await file.read()
    try:
        if filename.endswith((".txt", ".md")):
            text = content.decode("utf-8-sig", errors="replace")
        elif filename.endswith(".pdf"):
            try:
                from pypdf import PdfReader
                text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
            except ImportError as exc:
                raise ValueError("PDF 解析依赖未安装，请执行 pip install pypdf") from exc
        else:
            raise HTTPException(status_code=415, detail="课程资料仅支持 TXT、MD、PDF")
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            raise ValueError("资料没有可提取的文本")
        size, overlap = 700, 100
        chunks = [text[start:start + size] for start in range(0, len(text), size - overlap)]
        RAG_CHUNKS.extend({"doc": file.filename or "课程资料", "text": chunk} for chunk in chunks)
        RAG_DOCS.append(file.filename or "课程资料")
        return {"filename": file.filename, "chunks": len(chunks), "documents": list(dict.fromkeys(RAG_DOCS)), "message": "课程资料已加入知识库"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"资料处理失败：{exc}") from exc


class RAGChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    api_key: str | None = Field(default=None, max_length=300)
    base_url: str | None = Field(default=None, max_length=500)


def _retrieve_rag(question: str, limit: int = 4) -> list[dict[str, str]]:
    terms = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", question.lower()))
    scored = []
    for chunk in RAG_CHUNKS:
        words = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", chunk["text"].lower()))
        scored.append((len(terms & words), chunk))
    return [chunk for score, chunk in sorted(scored, key=lambda x: x[0], reverse=True)[:limit] if score > 0] or RAG_CHUNKS[:limit]


@app.post("/api/rag/chat")
async def rag_chat(payload: RAGChatRequest) -> dict[str, Any]:
    contexts = _retrieve_rag(payload.question)
    if not contexts:
        return {"answer": "知识库中还没有课程资料，请先上传 TXT、MD 或 PDF。", "warning": True, "sources": []}
    context = "\n\n".join(f"[{item['doc']}] {item['text']}" for item in contexts)
    prompt = f"你是课程知识库问答助手，只依据资料回答，不要编造。资料：\n{context}\n\n问题：{payload.question}\n请用中文简洁回答。"
    answer, error = await _deepseek(prompt, payload.api_key, payload.base_url)
    if not answer:
        answer = f"检索到的课程资料片段：\n{contexts[0]['text']}"
    return {"answer": answer, "warning": bool(error), "message": f"{error}，已返回检索片段" if error else None, "sources": list(dict.fromkeys(x["doc"] for x in contexts))}

def _report_markdown(students: list[dict[str, Any]]) -> str:
    fields = [("rain_classroom", "雨课堂平均观看率"), ("head_course", "头歌平均完成率"), ("mooc_score", "中国大学 MOOC 平均完成率"), ("chaoxing_score", "学习通平均作业得分")]
    def avg(field: str) -> str:
        values = [float(s.get(field, 0) or 0) for s in students]
        return f"{sum(values) / len(values):.1f}%" if values else "0.0%"
    severe = [s for s in students if min(float(s.get("rain_classroom", 0)), float(s.get("head_course", 0))) < 40]
    lines = ["# 班级学情分析报告", "", f"- 学生总数：{len(students)} 人", f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M')}", "", "## 平台表现", "", "| 指标 | 结果 |", "|---|---:|"]
    lines += [f"| {label} | {avg(field)} |" for field, label in fields]
    lines += ["", "## 严重落后名单", ""]
    lines += [f"- {s['name']}（{s['student_id']}）：雨课堂 {s.get('rain_classroom', 0)}%，头歌 {s.get('head_course', 0)}%，建议进行一对一跟进。" for s in severe] or ["- 暂无严重落后学生。"]
    lines += ["", "## 系统提醒建议", "", "1. 优先联系雨课堂与头歌任一平台低于 40% 的学生。", "2. 对 40%-60% 学生设置一周内补学目标并复查。", "3. 结合课程资料答疑记录，持续补充高频难点。"]
    return "\n".join(lines)


@app.get("/api/export-report")
async def export_report(format: str = Query("markdown", pattern="^(markdown|xlsx)$")) -> Response:
    students = CURRENT_DATA
    if format == "markdown":
        return Response(_report_markdown(students), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": "attachment; filename=learning-report.md"})
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(students).to_excel(writer, index=False, sheet_name="学生明细")
        denominator = max(1, len(students))
        summary = {"学生总数": len(students), "雨课堂平均观看率": sum(s.get("rain_classroom", 0) for s in students) / denominator, "头歌平均完成率": sum(s.get("head_course", 0) for s in students) / denominator, "MOOC平均完成率": sum(s.get("mooc_score", 0) for s in students) / denominator, "学习通平均得分": sum(s.get("chaoxing_score", 0) for s in students) / denominator}
        pd.DataFrame([summary]).to_excel(writer, index=False, sheet_name="班级汇总")
        severe = [s for s in students if min(s["rain_classroom"], s["head_course"]) < 40]
        pd.DataFrame(severe).to_excel(writer, index=False, sheet_name="严重落后")
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=learning-report.xlsx"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
