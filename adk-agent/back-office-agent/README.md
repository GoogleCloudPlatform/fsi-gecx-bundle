# ADK Agent

## Running Locally

```bash
# Create a virtual environment
uv venv --python 3.13 --clear

# Activate the environment
# shellcheck disable=SC1091
source .venv/bin/activate

poetry install
poetry lock

adk web
```
