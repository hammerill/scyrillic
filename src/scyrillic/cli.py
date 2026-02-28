from __future__ import annotations

import argparse
import base64
import sys
import time
import unicodedata
from pathlib import Path

OSC_SELECTION = "c"


def _osc52(data: bytes) -> bytes:
    # OSC 52: ESC ] 52 ; <selection> ; <base64> BEL
    payload = base64.b64encode(data)
    return b"\x1b]52;" + OSC_SELECTION.encode("ascii") + b";" + payload + b"\x07"


def copy_osc52(text: str) -> None:
    sys.stdout.buffer.write(_osc52(text.encode("utf-8")))
    sys.stdout.buffer.flush()


class ClipboardCoalescer:
    """
    Merge rapid consecutive REPL outputs into one clipboard payload.

    This keeps multiline paste usable even when terminals submit each line
    separately and each conversion would otherwise overwrite the clipboard.
    """

    def __init__(self, enabled: bool, burst_window_sec: float = 0.75):
        self.enabled = enabled and sys.stdout.isatty()
        self.burst_window_sec = burst_window_sec
        self._last_copy_at = 0.0
        self._last_payload = ""

    def copy(self, text: str, coalesce: bool = True) -> None:
        if not self.enabled:
            return

        now = time.monotonic()
        payload = text
        if coalesce and self._last_payload and now - self._last_copy_at <= self.burst_window_sec:
            sep = "\n" if text and not self._last_payload.endswith("\n") else ""
            payload = self._last_payload + sep + text

        copy_osc52(payload)
        self._last_copy_at = now
        self._last_payload = payload

    def reset(self) -> None:
        self._last_copy_at = 0.0
        self._last_payload = ""


def recode_segments(text: str, src_enc: str, dst_enc: str, errors: str = "replace") -> str:
    """
    Fix mojibake caused by bytes decoded with the wrong encoding.

    Default:
      src_enc="cp1252" (how the broken text appears)
      dst_enc="cp1251" (intended Cyrillic)

    Unicode-safe: characters not representable in src_enc are passed through unchanged.
    """
    # Accept decomposed input (e.g. A + combining diaeresis) from shell/paste
    # so it can be encoded as the expected single-byte source text.
    text = unicodedata.normalize("NFC", text)

    out: list[str] = []
    buf = bytearray()

    def flush() -> None:
        nonlocal buf
        if buf:
            out.append(buf.decode(dst_enc, errors=errors))
            buf.clear()

    for ch in text:
        try:
            b = ch.encode(src_enc)
        except UnicodeEncodeError:
            flush()
            out.append(ch)
            continue

        if len(b) != 1:
            flush()
            out.append(ch)
            continue

        buf.extend(b)

    flush()
    return "".join(out)


def convert(text: str, src_enc: str, dst_enc: str, errors: str) -> str:
    return recode_segments(text, src_enc=src_enc, dst_enc=dst_enc, errors=errors)


def _print_help() -> None:
    print(
        "Commands:\n"
        "  :q / :quit / :exit     Quit\n"
        "  :help                  Show this help\n"
        "  :enc                   Show current encodings\n"
        "  :from <enc>            Set source encoding (default cp1252)\n"
        "  :to <enc>              Set target encoding (default cp1251)\n"
        "  :paste                 (fallback REPL) enter multiline mode, end with a single '.' line\n"
        "\n"
        "Multiline:\n"
        "  - With prompt_toolkit installed: paste multiline text, press Enter to submit.\n"
        "  - Without it: use :paste and end with a line containing only '.'\n"
    )


def repl_fallback(src_enc: str, dst_enc: str, errors: str, do_copy: bool) -> int:
    print("scyrillic. Type :help for commands.\n")
    copier = ClipboardCoalescer(enabled=do_copy)
    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            continue

        s = line.strip()

        if s in (":q", ":quit", ":exit"):
            return 0
        if s in (":help",):
            copier.reset()
            _print_help()
            continue
        if s in (":enc",):
            copier.reset()
            print(f"from={src_enc}  to={dst_enc}  errors={errors}\n")
            continue

        if s.startswith(":from "):
            copier.reset()
            src_enc = s.split(None, 1)[1].strip()
            print(f"from={src_enc}\n")
            continue
        if s.startswith(":to "):
            copier.reset()
            dst_enc = s.split(None, 1)[1].strip()
            print(f"to={dst_enc}\n")
            continue

        if s == ":paste":
            copier.reset()
            lines: list[str] = []
            print("(paste mode) end with a single '.' line")
            while True:
                try:
                    l = input("... ")
                except EOFError:
                    print()
                    break
                if l == ".":
                    break
                lines.append(l)
            text = "\n".join(lines)
            out = convert(text, src_enc, dst_enc, errors)
            print(out)
            if out and not out.endswith("\n"):
                print()
            copier.copy(out, coalesce=False)
            continue

        out = convert(line, src_enc, dst_enc, errors)
        print(out)
        copier.copy(out)


def repl_prompt_toolkit(src_enc: str, dst_enc: str, errors: str, do_copy: bool) -> int:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings

    kb = KeyBindings()

    # Enter submits; Shift+Enter inserts newline.
    @kb.add("enter")
    def _(event) -> None:
        event.app.exit(result=event.app.current_buffer.text)

    @kb.add("s-enter")
    def _(event) -> None:
        event.app.current_buffer.insert_text("\n")

    session = PromptSession()
    copier = ClipboardCoalescer(enabled=do_copy)

    print("scyrillic. Type :help for commands.\n")
    while True:
        try:
            text = session.prompt(
                "> ",
                multiline=True,
                key_bindings=kb,
                prompt_continuation="... ",
            )
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        s = text.strip()

        if not s:
            continue
        if s in (":q", ":quit", ":exit"):
            return 0
        if s == ":help":
            copier.reset()
            _print_help()
            continue
        if s == ":enc":
            copier.reset()
            print(f"from={src_enc}  to={dst_enc}  errors={errors}\n")
            continue
        if s.startswith(":from "):
            copier.reset()
            src_enc = s.split(None, 1)[1].strip()
            print(f"from={src_enc}\n")
            continue
        if s.startswith(":to "):
            copier.reset()
            dst_enc = s.split(None, 1)[1].strip()
            print(f"to={dst_enc}\n")
            continue

        out = convert(text, src_enc, dst_enc, errors)
        print(out)
        if out and not out.endswith("\n"):
            print()
        copier.copy(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="scyrillic",
        description="Fix Scratch-2 style mojibake like 'Ðà...' back to Cyrillic for Scratch 3.",
    )
    p.add_argument("text", nargs="*", help="if provided, convert this text (otherwise REPL or stdin mode)")
    p.add_argument("--from-enc", dest="src_enc", default="cp1252")
    p.add_argument("--to-enc", dest="dst_enc", default="cp1251")
    p.add_argument("--errors", choices=["strict", "replace", "ignore"], default="replace")
    p.add_argument("--no-copy", action="store_true", help="do not copy result to clipboard via OSC 52")
    p.add_argument("--repl", action="store_true", help="force REPL mode")
    p.add_argument("--file", type=Path, help="read input from file (UTF-8)")
    args = p.parse_args(argv)

    do_copy = not args.no_copy

    if args.text:
        inp = " ".join(args.text)
        out = convert(inp, args.src_enc, args.dst_enc, args.errors)
        sys.stdout.write(out)
        if not out.endswith("\n"):
            sys.stdout.write("\n")
        if do_copy and sys.stdout.isatty():
            copy_osc52(out)
        return 0

    if args.file is not None:
        inp = args.file.read_text(encoding="utf-8")
        out = convert(inp, args.src_enc, args.dst_enc, args.errors)
        sys.stdout.write(out)
        if not out.endswith("\n"):
            sys.stdout.write("\n")
        if do_copy and sys.stdout.isatty():
            copy_osc52(out)
        return 0

    if not sys.stdin.isatty() and not args.repl:
        inp = sys.stdin.read()
        out = convert(inp, args.src_enc, args.dst_enc, args.errors)
        sys.stdout.write(out)
        if not out.endswith("\n"):
            sys.stdout.write("\n")
        if do_copy and sys.stdout.isatty():
            copy_osc52(out)
        return 0

    if sys.stdin.isatty():
        try:
            import prompt_toolkit  # noqa: F401
            return repl_prompt_toolkit(args.src_enc, args.dst_enc, args.errors, do_copy)
        except Exception:
            return repl_fallback(args.src_enc, args.dst_enc, args.errors, do_copy)

    return repl_fallback(args.src_enc, args.dst_enc, args.errors, do_copy)


if __name__ == "__main__":
    raise SystemExit(main())
