import subprocess
import logging
import os
import shutil
from mcp.server.fastmcp import FastMCP


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
            return "Execution successful. Video generated."
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


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    logger.info("Starting Manim MCP server (transport=%s)", transport)
    if transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")



