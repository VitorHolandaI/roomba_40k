#!/usr/bin/env python3
"""Thin entrypoint for local keyboard control."""

import os

from cli.controller import CliController
from roomba.interface import RoombaInterface

PORT = os.environ.get("ROOMBA_PORT", "/dev/ttyUSB0")


def main() -> None:
    controller = CliController(RoombaInterface(PORT))
    controller.run()


if __name__ == "__main__":
    main()
