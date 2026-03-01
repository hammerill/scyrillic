# scyrillic

Python script to convert broken Scratch 2 Cyrillic text back to normal for Scratch 3.

## How to Use It

You can pipe text into it:

```bash
echo "Äîáàâèòü ôðàçó" | scyrillic
# Добавить фразу
```

Or pass text as arguments:

```bash
scyrillic "Äîáàâèòü ôðàçó"
# Добавить фразу
```

But the easiest way to use it is REPL, paste the garbage text, press Enter, the corrected text gets copied to your clipboard, repeat:

```bash
scyrillic
# this launches the REPL interface you can use as explained above
```

Refer to `scyrillic -h` for more info.

## Install

Install as a [uv tool](https://docs.astral.sh/uv) from this GitHub repo:

```bash
uv tool install git+https://github.com/hammerill/scyrillic
```

Or local dev install:

```bash
# in scyrillic project folder
uv tool install -e .
```
