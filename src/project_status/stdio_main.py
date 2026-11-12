"""Local transport: MCP over stdio. Identity is the OS/user running the process."""
import getpass, os

from .backend import InProcessBackend
from .server import build_server


def main() -> None:
    user = os.environ.get("GMO_USER") or getpass.getuser()
    build_server(InProcessBackend(), lambda: user, transport="stdio").run(transport="stdio")


if __name__ == "__main__":
    main()
