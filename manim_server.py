import logging
import mimetypes
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(open("/dev/stderr", "w"))],
)
logger = logging.getLogger("manim-mcp")

mcp = FastMCP(
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8000")),
)

MANIM_EXECUTABLE = os.getenv("MANIM_EXECUTABLE", "manim")
# l/m/h/k/p — lower quality uses less RAM (important for small containers; default l)
_MANIM_Q = (os.getenv("MANIM_QUALITY", "l") or "l").strip().lower()[:1]
MANIM_QUALITY_FLAG = f"-q{_MANIM_Q}" if _MANIM_Q in ("l", "m", "h", "k", "p") else "-ql"
# Set MANIM_PREVIEW_OPEN=0 in headless deploys to skip -p (open player after render)
_MANIM_PREVIEW = (os.getenv("MANIM_PREVIEW_OPEN", "1") or "1").strip().lower() not in (
    "0",
    "false",
    "no",
)

TEMP_DIRS = {}
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
os.makedirs(BASE_DIR, exist_ok=True)

logger.info("Manim MCP server initializing")
logger.info("MANIM_EXECUTABLE = %s", MANIM_EXECUTABLE)
logger.info("render flags: %s preview_open=%s", MANIM_QUALITY_FLAG, _MANIM_PREVIEW)
logger.info("BASE_DIR = %s", BASE_DIR)


def _supabase_upload_configured() -> bool:
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "").strip()
    bucket = (os.getenv("SUPABASE_STORAGE_BUCKET") or "").strip()
    return bool(url and key and bucket)


def _normalize_storage_prefix(raw: str | None) -> str:
    p = (raw or "").strip()
    if not p:
        return ""
    return p if p.endswith("/") else p + "/"


def _collect_render_artifacts(root: Path) -> list[Path]:
    """Final outputs only — skip Manim partial frame segments (large, not useful in object storage)."""
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts = p.parts
        if "partial_movie_files" in parts:
            continue
        suf = p.suffix.lower()
        if suf in (".mp4", ".png", ".gif", ".svg", ".jpg", ".jpeg", ".webp"):
            out.append(p)
    return sorted(out)


def _guess_content_type(path: Path) -> str:
    ct, _ = mimetypes.guess_type(str(path))
    return ct or "application/octet-stream"


def _storage_access_url(
    supabase: Any,
    bucket: str,
    object_path: str,
    *,
    public: bool,
    signed_expires: int,
) -> str:
    """Return a public URL or a time-limited signed URL depending on bucket policy."""
    sb = supabase.storage.from_(bucket)
    if public:
        r = sb.get_public_url(object_path)
        if isinstance(r, dict):
            return str(r.get("publicUrl") or r.get("publicURL") or "")
        return getattr(r, "publicUrl", None) or str(r)
    r = sb.create_signed_url(object_path, signed_expires)
    if isinstance(r, dict):
        u = (
            r.get("signedURL")
            or r.get("signedUrl")
            or r.get("signed_url")
        )
        if u:
            return str(u)
        data = r.get("data")
        if isinstance(data, dict):
            u2 = data.get("signedUrl") or data.get("signedURL")
            if u2:
                return str(u2)
    return ""


def _upload_artifacts_to_supabase(tmpdir: Path) -> tuple[list[str], list[str]]:
    """Upload artifacts to Supabase Storage. Returns (lines for tool message, errors)."""
    try:
        from supabase import create_client  # type: ignore[import-untyped]
    except ImportError:
        return ([], ["supabase package not installed (add supabase>=2 to dependencies)"])

    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "").strip()
    bucket = (os.getenv("SUPABASE_STORAGE_BUCKET") or "").strip()
    prefix = _normalize_storage_prefix(os.getenv("SUPABASE_STORAGE_PREFIX", "manim-renders/"))
    # Default: public bucket URLs (get_public_url). Set SUPABASE_STORAGE_PUBLIC=0 for private buckets + signed URLs.
    _pub = (os.getenv("SUPABASE_STORAGE_PUBLIC") or "").strip().lower()
    if not _pub:
        public = True
    else:
        public = _pub not in ("0", "false", "no")
    try:
        signed_expires = int((os.getenv("SUPABASE_SIGNED_URL_EXPIRES_SECONDS") or "604800").strip())
    except ValueError:
        signed_expires = 604800

    if not url or not key or not bucket:
        return ([], ["Supabase env incomplete (need SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET)"])

    run_id = uuid.uuid4().hex
    base_prefix = f"{prefix}{run_id}/"

    client = create_client(url, key)
    lines: list[str] = []
    errors: list[str] = []

    artifacts = _collect_render_artifacts(tmpdir)
    if not artifacts:
        return (
            ["(no image/video files found under render directory to upload)"],
            [],
        )

    for local in artifacts:
        try:
            rel = local.relative_to(tmpdir).as_posix()
        except ValueError:
            rel = local.name
        object_path = f"{base_prefix}{rel}"
        content_type = _guess_content_type(local)
        data = local.read_bytes()
        try:
            client.storage.from_(bucket).upload(
                object_path,
                data,
                file_options={
                    "content-type": content_type,
                    "upsert": "true",
                },
            )
        except Exception as exc:
            err = f"{rel}: {exc}"
            errors.append(err)
            logger.exception("Supabase upload failed for %s", object_path)
            continue
        access = _storage_access_url(
            client,
            bucket,
            object_path,
            public=public,
            signed_expires=signed_expires,
        )
        if access:
            lines.append(f"- {rel} → {access}")
        else:
            lines.append(f"- {rel} (uploaded to `{object_path}` in bucket `{bucket}`)")
        logger.info("Uploaded to Supabase Storage: %s", object_path)

    return (lines, errors)


@mcp.tool()
def execute_manim_code(manim_code: str) -> str:
    """Execute the Manim code"""
    tmpdir = os.path.join(BASE_DIR, "manim_tmp")
    os.makedirs(tmpdir, exist_ok=True)
    script_path = os.path.join(tmpdir, "scene.py")

    logger.info("execute_manim_code called — writing script to %s", script_path)

    try:
        with open(script_path, "w") as script_file:
            script_file.write(manim_code)

        cmd = [MANIM_EXECUTABLE, MANIM_QUALITY_FLAG]
        if _MANIM_PREVIEW:
            cmd.append("-p")
        cmd.append(script_path)
        logger.info("Running: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )

        if result.returncode == 0:
            TEMP_DIRS[tmpdir] = True
            logger.info("Manim execution succeeded — output at %s", tmpdir)
            msg = "Execution successful. Video generated."
            if _supabase_upload_configured():
                upload_lines, upload_errors = _upload_artifacts_to_supabase(Path(tmpdir))
                if upload_lines or upload_errors:
                    msg += "\n\nSupabase Storage:\n"
                    if upload_lines:
                        msg += "\n".join(upload_lines)
                    if upload_errors:
                        msg += "\n" + "\n".join(upload_errors)
            return msg
        else:
            logger.error("Manim execution failed (exit %d): %s", result.returncode, result.stderr)
            rc = result.returncode
            hint = ""
            # Negative codes: -N = killed by signal N (e.g. -9 = SIGKILL). 137 = 128+9.
            if rc == -9 or rc == 137:
                hint = (
                    " The process was killed (SIGKILL), often due to out-of-memory in the container. "
                    "Set MANIM_QUALITY=l (default) or simplify the scene; increase memory limit if you can."
                )
            return f"Execution failed (exit {rc}): {result.stderr}{hint}"

    except Exception as e:
        logger.exception("Error during execution")
        return f"Error during execution: {str(e)}"


@mcp.tool()
def cleanup_manim_temp_dir(directory: str) -> str:
    """Clean up the specified Manim temporary directory after execution."""
    logger.info("cleanup_manim_temp_dir called for %s", directory)
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            logger.info("Cleaned up %s", directory)
            return f"Cleanup successful for directory: {directory}"
        else:
            logger.warning("Directory not found: %s", directory)
            return f"Directory not found: {directory}"
    except Exception as e:
        logger.exception("Failed to clean up %s", directory)
        return f"Failed to clean up directory: {directory}. Error: {str(e)}"


if _supabase_upload_configured():
    logger.info(
        "Supabase Storage uploads enabled (bucket=%s, prefix=%s)",
        os.getenv("SUPABASE_STORAGE_BUCKET"),
        _normalize_storage_prefix(os.getenv("SUPABASE_STORAGE_PREFIX", "manim-renders/")),
    )


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    logger.info("Starting Manim MCP server (transport=%s)", transport)
    if transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
