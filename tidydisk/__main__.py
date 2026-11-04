import sys


def run() -> int:
    cmds = ("status", "scan", "analyze", "clean", "report", "notify", "schedule", "ai", "background", "diag", "changes", "config", "rules",
            "history", "-h", "--help", "-V", "--version", "-q", "--quiet", "--config")
    if len(sys.argv) > 1 and sys.argv[1] in cmds:
        from .cli import main as cli_main

        return cli_main()
    from .gui import main

    return main()


def main() -> None:
    code = run()
    if len(sys.argv) > 1 and sys.argv[1] in ("ai", "background"):
        # wyniki sa zapisane; porzucone zapytania do AI (watki) nie moga wstrzymac wyjscia az do konca limitu czasu
        import os

        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(int(code or 0))
    sys.exit(code)


if __name__ == "__main__":
    main()
