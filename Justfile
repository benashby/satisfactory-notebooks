PID_FILE := ".jupyter.pid"
PORT     := "8888"
JUPYTER  := ".venv/bin/jupyter"

# List available recipes
default:
    @just --list

# Create the venv and install the entire Python stack (run once after cloning)
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    # The .venv owns the WHOLE python stack — the Nix flake (satisfactory.nix) provides
    # no python on purpose. A Nix-provided python exports PYTHONPATH over all its store
    # site-packages, which JupyterLab inherits and passes to every kernel, shadowing this
    # venv so pip-installed packages become invisible to kernels. With no Nix python,
    # there's no PYTHONPATH; uv provisions its own standalone CPython here.
    #
    # No --system-site-packages: there are no system site-packages worth sharing, and
    # the flag is what let the old Nix python leak in. Full isolation is the point.
    if [ ! -f ".venv/bin/jupyter" ]; then
        echo "Creating venv..."
        uv venv .venv
    fi
    echo "Installing python stack..."
    # jupyterlab + sci stack + plotly: the notebooks' runtime deps (previously from Nix).
    # jupyter-mcp-server: the MCP backend. We deliberately do NOT install jupyter-ai —
    # its 3.x line hard-requires jupyter-server-documents, whose YDoc output rerouting
    # breaks the MCP's execute path (timeouts) and throws "File ID error" in the UI.
    # Use Claude Code + the MCP instead of in-Lab Jupyternaut.
    uv pip install --python .venv/bin/python \
        jupyterlab ipykernel numpy pandas matplotlib scipy plotly jupyter-mcp-server pulp graphviz pytest
    # Register the venv as the default `python3` kernel so notebooks run THIS interpreter
    # (the one with all the packages), not some other python jupyter might discover.
    .venv/bin/python -m ipykernel install --prefix .venv --name python3 \
        --display-name "Python 3 (satisfactory)"
    echo "Done. Run: just start"

# Run all tests
test:
    env -u PYTHONPATH .venv/bin/pytest tests/ -v

# Start JupyterLab server in background
start:
    #!/usr/bin/env bash
    if [ ! -f "{{JUPYTER}}" ]; then
        echo "Run 'just setup' first to create the venv"
        exit 1
    fi
    if [ -f "{{PID_FILE}}" ] && kill -0 "$(cat {{PID_FILE}})" 2>/dev/null; then
        echo "JupyterLab already running (PID $(cat {{PID_FILE}}))"
        echo "  → http://localhost:{{PORT}}"
        exit 0
    fi
    # Clear PYTHONPATH so kernels use the venv, not whatever the ambient shell leaks.
    # The flake provides no python (satisfactory.nix), but this is belt-and-suspenders:
    # any inherited PYTHONPATH would shadow the venv and hide pip-installed packages.
    unset PYTHONPATH
    GV=$(nix-build '<nixpkgs>' -A graphviz --no-out-link 2>/dev/null)
    [ -n "$GV" ] && export PATH="$GV/bin:$PATH"
    nohup {{JUPYTER}} lab --no-browser --port={{PORT}} --IdentityProvider.token='' --ServerApp.disable_check_xsrf=True > .jupyter.log 2>&1 &
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

# Execute notebook and save outputs in-place (auto-trusts so HTML/JS renders in JupyterLab)
# env -u PYTHONPATH: the devshell's python language exports PYTHONPATH, which would
# shadow the venv in the spawned kernel and hide pip-installed packages (e.g. plotly).
# GV: adds graphviz dot binary to PATH so graph.py can render SVG inline.
run notebook="index.ipynb":
    #!/usr/bin/env bash
    GV=$(nix-build '<nixpkgs>' -A graphviz --no-out-link 2>/dev/null)
    [ -n "$GV" ] && export PATH="$GV/bin:$PATH"
    env -u PYTHONPATH {{JUPYTER}} nbconvert --to notebook --execute --inplace {{notebook}}
    {{JUPYTER}} trust {{notebook}}

# Render a notebook to HTML (output: <name>.html)
render notebook="index.ipynb":
    env -u PYTHONPATH {{JUPYTER}} nbconvert --to html --execute {{notebook}}
    @echo "→ $(basename {{notebook}} .ipynb).html"

# Render all notebooks to HTML
render-all:
    env -u PYTHONPATH {{JUPYTER}} nbconvert --to html --execute *.ipynb
    @echo "→ rendered all notebooks"

# Open the HTML render in the default browser (renders first if HTML doesn't exist)
open notebook="index.ipynb":
    #!/usr/bin/env bash
    html="$(basename {{notebook}} .ipynb).html"
    if [ ! -f "$html" ]; then
        just render {{notebook}}
    fi
    xdg-open "$html"

# Run then open in browser
view notebook="index.ipynb":
    just render {{notebook}}
    just open {{notebook}}
