PID_FILE := ".jupyter.pid"
PORT     := "8888"
JUPYTER  := ".venv/bin/jupyter"

# List available recipes
default:
    @just --list

# Create venv and install jupyter-ai (run once after cloning)
setup:
    #!/usr/bin/env bash
    if [ ! -f ".venv/bin/jupyter" ]; then
        echo "Creating venv..."
        uv venv --system-site-packages .venv
    fi
    echo "Installing jupyter-ai..."
    uv pip install --python .venv/bin/python 'jupyter-ai[jupyternaut]' jupyter-mcp-server
    echo "Done. Run: just start"

# Start JupyterLab server in background
start:
    #!/usr/bin/env bash
    if [ ! -f "{{JUPYTER}}" ]; then
        echo "Run 'just setup' first to install jupyter-ai"
        exit 1
    fi
    if [ -f "{{PID_FILE}}" ] && kill -0 "$(cat {{PID_FILE}})" 2>/dev/null; then
        echo "JupyterLab already running (PID $(cat {{PID_FILE}}))"
        echo "  → http://localhost:{{PORT}}"
        exit 0
    fi
    nohup {{JUPYTER}} lab --no-browser --port={{PORT}} --IdentityProvider.token='' > .jupyter.log 2>&1 &
    echo $! > {{PID_FILE}}
    echo "JupyterLab started (PID $!)"
    sleep 2
    grep -o 'http://localhost:{{PORT}}/lab?token=[^ ]*' .jupyter.log | tail -1 || \
        echo "  → check .jupyter.log for the token URL"

# Stop JupyterLab server
stop:
    #!/usr/bin/env bash
    if [ ! -f "{{PID_FILE}}" ]; then
        echo "No PID file found — nothing to stop"
        exit 0
    fi
    PID=$(cat {{PID_FILE}})
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "JupyterLab stopped (PID $PID)"
    else
        echo "Process $PID not running"
    fi
    rm -f {{PID_FILE}}

# Show JupyterLab status and token URL
status:
    #!/usr/bin/env bash
    if [ -f "{{PID_FILE}}" ] && kill -0 "$(cat {{PID_FILE}})" 2>/dev/null; then
        echo "Running (PID $(cat {{PID_FILE}}))"
        grep -o 'http://localhost:{{PORT}}/lab?token=[^ ]*' .jupyter.log | tail -1
    else
        echo "Not running"
    fi

# Execute notebook and save outputs in-place
run notebook="power_grid.ipynb":
    {{JUPYTER}} nbconvert --to notebook --execute --inplace {{notebook}}

# Render a notebook to HTML (output: <name>.html)
render notebook="power_grid.ipynb":
    {{JUPYTER}} nbconvert --to html --execute {{notebook}}
    @echo "→ $(basename {{notebook}} .ipynb).html"

# Render all notebooks to HTML
render-all:
    {{JUPYTER}} nbconvert --to html --execute *.ipynb
    @echo "→ rendered all notebooks"

# Open the HTML render in the default browser (renders first if HTML doesn't exist)
open notebook="power_grid.ipynb":
    #!/usr/bin/env bash
    html="$(basename {{notebook}} .ipynb).html"
    if [ ! -f "$html" ]; then
        just render {{notebook}}
    fi
    xdg-open "$html"

# Run then open in browser
view notebook="power_grid.ipynb":
    just render {{notebook}}
    just open {{notebook}}
