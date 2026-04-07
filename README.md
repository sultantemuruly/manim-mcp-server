# Manim MCP Server

![Manim MCP Demo](Demo-manim-mcp.gif)


## Overview

This is an MCP (Model Context Protocol) server that executes Manim animation code and returns the generated video. It allows users to send Manim scripts and receive the rendered animation.

## Features

- Executes Manim Python scripts.
- Saves animation output in a visible media folder.
- Allows users to clean up temporary files after execution.
- Portable and configurable via environment variables.

## Installation

### Prerequisites

Ensure you have the following installed:

- Python 3.8+
- Manim (Community Version)
- MCP

### Install Manim

```sh
pip install manim
```

### Install MCP

```sh
pip install mcp
```

### Clone the Repository

```sh
git clone https://github.com/abhiemj/manim-mcp-server.git
cd manim-mcp-server
```

## Integration with Claude

To integrate the Manim MCP server with Claude, add the following to your `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
     "manim-server": {
      "command": "/absolute/path/to/python",
      "args": [
        "/absolute/path/to/manim-mcp-server/manim_server.py"
      ],
      "env": {
        "MANIM_EXECUTABLE": "/Users/[Your_username]/anaconda3/envs/manim2/Scripts/manim.exe"
      }
    }
  }
}
```

### Finding Your Python Path

To find your Python executable path, use the following command:

#### Windows (PowerShell):
```sh
(Get-Command python).Source
```

#### Windows (Command Prompt/Terminal):
```sh
where python
```

#### Linux/macOS (Terminal):
```sh
which python
```

This ensures that Claude can communicate with the Manim MCP server to generate animations dynamically.

## Contributing

1. Fork the repository.
2. Create a new branch:
   ```sh
   git checkout -b add-feature
   ```
3. Make changes and commit:
   ```sh
   git commit -m "Added a new feature"
   ```
4. Push to your fork:
   ```sh
   git push origin add-feature
   ```
5. Open a pull request.

## License

This MCP server is licensed under the MIT License. This means you are free to use, modify, and distribute the software, subject to the terms and conditions of the MIT License. For more details, please see the LICENSE file in the project repository.

## Author

Created by **[abhiemj](https://github.com/abhiemj)**. Contributions welcome! 🚀

### **Listed in Awesome MCP Servers**  
This repository is featured in the [Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers) repository under the **Animation & Video** category. Check it out along with other great MCP server implementations!


## **Acknowledgments**  
- Thanks to the [Manim Community](https://www.manim.community/) for their amazing animation library.  
- Inspired by the open-source MCP ecosystem.

## Find me at
<a href="https://www.instagram.com/aiburner_official" target="blank"><img align="center" src="https://raw.githubusercontent.com/rahuldkjain/github-profile-readme-generator/master/src/images/icons/Social/instagram.svg" alt="aiburner_official" height="30" width="40" /></a>
@aiburner_official

---

## Docker and cloud deployment

> This repository is a fork of [abhiemj/manim-mcp-server](https://github.com/abhiemj/manim-mcp-server) with additions for containerized cloud deployment.

The Docker setup lets you run the Manim MCP server as a long-lived service without installing Manim or LaTeX locally. The image is built on top of [`manimcommunity/manim`](https://hub.docker.com/r/manimcommunity/manim) (Manim, FFmpeg, Cairo, and LaTeX included). Only the MCP Python SDK and [`manim_server.py`](manim_server.py) are added on top.

**Transport.** When run directly, the server defaults to **stdio** (for local MCP clients like Claude Desktop). Docker and cloud setups use **streamable HTTP** so clients can reach the server over the network. The [`docker-compose.yml`](docker-compose.yml) sets `MCP_TRANSPORT=streamable-http` explicitly, which takes precedence over any local `.env` values.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2

### Quick start

1. Copy the environment template and adjust if needed:

   ```sh
   cp .env.example .env
   ```

   > The container itself does not need `OPENAI_API_KEY`. That variable is only used by [`agent.py`](agent.py) for the local Gradio demo.

2. Build and start:

   ```sh
   docker compose up --build
   ```

3. The server listens on **port 8000** at the **`/mcp`** path (e.g. `http://localhost:8000/mcp`). Rendered videos are written to `/app/media` inside the container; the compose file mounts `./media` on the host so output persists across restarts.

### Running without Compose

```sh
docker build -t manim-mcp-server .
docker run -p 8000:8000 -v "$(pwd)/media:/app/media" manim-mcp-server
```

Override defaults with `-e` flags (e.g. `-e MCP_PORT=9000`) if your platform assigns a different port.

### Security note

> **Warning:** This service executes arbitrary Manim (Python) code submitted by clients. Exposing it on a public URL without protection is dangerous.

Use a private network, edge authentication (reverse proxy, API gateway, or your platform's built-in controls), and appropriate resource limits.
