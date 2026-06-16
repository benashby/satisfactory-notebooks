PID_FILE := ".jupyter.pid"
PORT     := "8888"

# List available recipes
default:
    @just --list

# Start JupyterLab server in background
start:
    #!/usr/bin/env bash
    if [ -f "{{PID_FILE}}" ] && kill -0 "$(cat {{PID_FILE}})" 2>/dev/null; then
        echo "JupyterLab already running (PID $(cat {{PID_FILE}}))"
        echo "  → http://localhost:{{PORT}}"
        exit 0
    fi
    nohup jupyter lab --no-browser --port={{PORT}} > .jupyter.log 2>&1 &
    echo $! > {{PID_FILE}}
    echo "JupyterLab started (PID $!)"
    sleep 2
    # Print the token URL from the log
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

# Execute all notebooks and save outputs in-place
run notebook="power_grid.ipynb":
    jupyter nbconvert --to notebook --execute --inplace {{notebook}}

# Render a notebook to HTML (output: <name>.html)
render notebook="power_grid.ipynb":
    jupyter nbconvert --to html --execute {{notebook}}
    @echo "→ $(basename {{notebook}} .ipynb).html"

# Render all notebooks to HTML
render-all:
    jupyter nbconvert --to html --execute *.ipynb
    @echo "→ rendered all notebooks"

# Open the HTML render in the default browser
open notebook="power_grid.ipynb":
    xdg-open "$(basename {{notebook}} .ipynb).html"

# Run then open in browser
view notebook="power_grid.ipynb":
    just render {{notebook}}
    just open {{notebook}}
