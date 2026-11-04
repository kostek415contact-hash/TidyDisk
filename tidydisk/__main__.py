import sys


def run() -> int:
    cmds = ("status", "scan", "analyze", "clean", "report", "notify", "schedule", "ai", "background", "diag", "changes", "config", "rules",
            "history", "-h", "--help", "-V", "--version", "-q", "--quiet", "--config")
    if len(sys.argv) > 1 and sys.argv[1] in cmds:
        from .cli import main as cli_main

        return cli_main()
    try:
        from .gui import main
    except ImportError:  # wersja konsolowa (.exe bez PyQt6)
        sys.stderr.write("Wersja konsolowa bez okna: tidydisk status | scan | report | config | rules | --help\n")
        return 2
    return main()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # konsola Windows (cp852/cp1250) nie moze wywalic programu na znaku spoza strony kodowej
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    code = run()
    if len(sys.argv) > 1 and sys.argv[1] in ("ai", "background"):
        # wyniki sa zapisane; porzucone zapytania do AI (watki) nie moga wstrzymac wyjscia az do konca limitu czasu
        import os

        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except (AttributeError, OSError, ValueError):
                pass
        os._exit(int(code or 0))
    sys.exit(code)


if __name__ == "__main__":
    main()
