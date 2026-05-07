# Compliance Diff Engine

Python implementation of the staged compliance diff challenge in `BUILD.md`.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env` for real OpenAI structured-output calls.

## Run

```bash
python pipeline.py
python validate.py
```

For local structural testing without an API key:

```bash
python pipeline.py --mock-llm
python validate.py
```

The mock mode is deterministic and exists only for local dry runs; the normal path uses the OpenAI SDK.
