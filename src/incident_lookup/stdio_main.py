import getpass, os

from .server import build_server


def main() -> None:
    user = os.environ.get("GMO_USER") or getpass.getuser()
    build_server(lambda: user, transport="stdio").run(transport="stdio")


if __name__ == "__main__":
    main()
