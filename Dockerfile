FROM manimcommunity/manim:latest

USER root

# Install MCP package (Manim, FFmpeg, Cairo, LaTeX already in base image)
RUN pip install --no-cache-dir "mcp[cli]>=1.27.0" "supabase>=2.0.0"

WORKDIR /app

COPY manim_server.py .

# Persistent media output directory — mount a volume here in production
RUN mkdir -p /app/media

ENV MANIM_EXECUTABLE=manim \
    MANIM_QUALITY=l \
    MANIM_PREVIEW_OPEN=0 \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

EXPOSE 8000

CMD ["python", "manim_server.py"]
