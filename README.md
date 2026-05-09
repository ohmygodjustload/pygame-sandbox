# pygame-sandbox

Small pygame experiments.

## Files

- `hello.py` — minimal pygame "hello world".
- `seven_segment.py` — animated 7-segment digit demo.
- `toyota_cressida.py` — recreation of the 1982 Toyota Cressida TRONIX cluster.
- `dashboard.py` — retro 80s digital dashboard (curved cyan speedometer,
  diagnostic / trip panels, tachometer with pink redline). Idles with
  animated drift on every gauge; no input required.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python dashboard.py     # or any of the other files above
```

Press `ESC` or close the window to quit.
