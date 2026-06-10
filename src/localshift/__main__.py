"""LocalShift runner entrypoint — `python -m localshift` and the `localshift`
console-script both delegate here (pyproject: localshift = localshift.__main__:main)."""
from localshift.cli import main

if __name__ == "__main__":
    main()
