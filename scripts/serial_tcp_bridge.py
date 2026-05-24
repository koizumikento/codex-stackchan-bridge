from __future__ import annotations

import argparse
import selectors
import socket
import sys
import time

import serial


def add_control_line_argument(
    parser: argparse.ArgumentParser,
    name: str,
    help_text: str,
) -> None:
    parser.add_argument(
        f"--{name}",
        choices=("inactive", "active", "unchanged"),
        default="inactive",
        help=help_text,
    )


def open_serial_port(args: argparse.Namespace) -> serial.Serial:
    ser = serial.Serial()
    ser.port = args.serial_port
    ser.baudrate = args.baud
    ser.timeout = 0
    ser.write_timeout = 0
    if args.dtr != "unchanged":
        ser.dtr = args.dtr == "active"
    if args.rts != "unchanged":
        ser.rts = args.rts == "active"
    ser.open()
    return ser


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bridge a host serial port to one TCP client."
    )
    parser.add_argument("--serial-port", required=True, help="Host serial port, e.g. COM3.")
    parser.add_argument("--baud", type=int, default=921600, help="Serial baud rate.")
    parser.add_argument("--host", default="127.0.0.1", help="TCP bind host.")
    parser.add_argument("--tcp-port", type=int, default=11411, help="TCP bind port.")
    parser.add_argument(
        "--quiet-timeout",
        type=float,
        default=0.2,
        help="Selector timeout in seconds.",
    )
    parser.add_argument(
        "--one-shot",
        action="store_true",
        help="Exit after the first TCP client disconnects.",
    )
    add_control_line_argument(
        parser,
        "dtr",
        (
            "DTR state to apply before opening the serial port. The default "
            "keeps ESP32-S3 auto-reset lines inactive during runtime Agent "
            "bridging."
        ),
    )
    add_control_line_argument(
        parser,
        "rts",
        (
            "RTS state to apply before opening the serial port. The default "
            "keeps ESP32-S3 auto-boot/reset lines inactive during runtime "
            "Agent bridging."
        ),
    )
    args = parser.parse_args()

    with open_serial_port(args) as ser:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((args.host, args.tcp_port))
            server.listen(1)
            print(
                f"serial_tcp_bridge listening {args.host}:{args.tcp_port} "
                f"<-> {args.serial_port}@{args.baud} "
                f"dtr={args.dtr} rts={args.rts}",
                flush=True,
            )
            while True:
                conn, addr = server.accept()
                with conn:
                    print(f"serial_tcp_bridge client connected {addr}", flush=True)
                    conn.setblocking(False)
                    selector = selectors.DefaultSelector()
                    selector.register(conn, selectors.EVENT_READ, "tcp")
                    last_report = time.monotonic()
                    serial_to_tcp = 0
                    tcp_to_serial = 0

                    while True:
                        try:
                            waiting = ser.in_waiting
                            if waiting:
                                data = ser.read(waiting)
                                if data:
                                    conn.sendall(data)
                                    serial_to_tcp += len(data)

                            for key, _ in selector.select(args.quiet_timeout):
                                if key.data != "tcp":
                                    continue
                                data = conn.recv(4096)
                                if not data:
                                    raise ConnectionResetError("client disconnected")
                                ser.write(data)
                                tcp_to_serial += len(data)
                        except (BrokenPipeError, ConnectionResetError):
                            print("serial_tcp_bridge client disconnected", flush=True)
                            break

                        now = time.monotonic()
                        if now - last_report >= 5.0:
                            print(
                                "serial_tcp_bridge bytes "
                                f"serial_to_tcp={serial_to_tcp} tcp_to_serial={tcp_to_serial}",
                                flush=True,
                            )
                            last_report = now
                if args.one_shot:
                    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except serial.SerialException as exc:
        print(f"serial_tcp_bridge serial error: {exc}", file=sys.stderr)
        raise SystemExit(1)
