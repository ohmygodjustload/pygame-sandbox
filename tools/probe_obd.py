#!/usr/bin/env python3
"""
OBD-II capability and throughput probe for the Odyssey cluster project.

Answers the two questions that decide how the real dash has to be built:

  1. Which signals can this vehicle actually supply?
  2. How many values per second can the bus deliver?

The second one matters more than people expect. A 2006 Odyssey is most likely
ISO 9141-2 (10.4 kbaud K-line), where an ELM327 delivers roughly 5-20 requests
per second in total across every PID -- not per PID. That number sets how
responsive the tachometer can be and forces interpolation in the render loop.

Usage
-----
    # No hardware at all - exercises the whole tool against a simulated
    # 2006 Honda on a slow K-line bus.
    python tools/probe_obd.py --mock

    # Real adapter, auto-detect port and baud
    python tools/probe_obd.py

    # Explicit
    python tools/probe_obd.py --port /dev/ttyUSB0 --baud 38400
    python tools/probe_obd.py --list-ports
    python tools/probe_obd.py --json obd_report.json --duration 15

    # Against ELM327-emulator (pip install py-obdii[sim])
    python -m elm -s car            # prints the pty it created
    python tools/probe_obd.py --port /dev/pts/N

Run the engine while probing, otherwise RPM/speed/load read zero and the
throughput numbers are still valid but the values are not.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # --mock still works without pyserial
    serial = None
    list_ports = None


BAUD_CANDIDATES = (38400, 9600, 115200, 500000)
PROMPT = b">"


# ---------------------------------------------------------------------------
# PID table
# ---------------------------------------------------------------------------


def _u8(b: bytes, i: int = 0) -> int:
    return b[i]


def _u16(b: bytes, i: int = 0) -> int:
    return (b[i] << 8) | b[i + 1]


def _c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


@dataclass(frozen=True)
class Pid:
    pid: int
    name: str
    unit: str
    decode: Callable[[bytes], float]
    dash_field: str = ""
    note: str = ""
    also_f: bool = False          # temperature: show Fahrenheit alongside

    @property
    def cmd(self) -> str:
        return f"01{self.pid:02X}"


# Curated to what this dashboard needs, plus a few worth knowing about.
PROJECT_PIDS: tuple[Pid, ...] = (
    Pid(0x04, "Calculated engine load", "%", lambda b: _u8(b) * 100.0 / 255.0, "throttle proxy"),
    Pid(0x05, "Engine coolant temp", "C", lambda b: _u8(b) - 40.0, "coolant_f", also_f=True),
    Pid(0x0B, "Intake manifold pressure", "kPa", lambda b: float(_u8(b)), "oil_psi substitute",
        note="repurpose the oil bar as MAP"),
    Pid(0x0C, "Engine RPM", "rpm", lambda b: _u16(b) / 4.0, "rpm"),
    Pid(0x0D, "Vehicle speed", "km/h", lambda b: float(_u8(b)), "speed"),
    Pid(0x0F, "Intake air temp", "C", lambda b: _u8(b) - 40.0, "", also_f=True),
    Pid(0x10, "MAF air flow", "g/s", lambda b: _u16(b) / 100.0, "avg_mpg / dte",
        note="fuel burn from MAF when 0x5E is absent"),
    Pid(0x11, "Throttle position", "%", lambda b: _u8(b) * 100.0 / 255.0, ""),
    Pid(0x1F, "Run time since start", "s", lambda b: float(_u16(b)), ""),
    Pid(0x2F, "Fuel tank level", "%", lambda b: _u8(b) * 100.0 / 255.0, "fuel",
        note="often coarse/steppy on Hondas"),
    Pid(0x33, "Barometric pressure", "kPa", lambda b: float(_u8(b)), ""),
    Pid(0x42, "Control module voltage", "V", lambda b: _u16(b) / 1000.0, "volts"),
    Pid(0x43, "Absolute load", "%", lambda b: _u16(b) * 100.0 / 255.0, ""),
    Pid(0x46, "Ambient air temp", "C", lambda b: _u8(b) - 40.0, "outside_f", also_f=True),
    Pid(0x5C, "Engine oil temp", "C", lambda b: _u8(b) - 40.0, "", also_f=True,
        note="rare before 2008"),
    Pid(0x5E, "Engine fuel rate", "L/h", lambda b: _u16(b) / 20.0, "avg_mpg / dte",
        note="ideal for mpg; rare before 2008"),
)

PID_BY_NUM = {p.pid: p for p in PROJECT_PIDS}

@dataclass(frozen=True)
class DashField:
    name: str
    kind: str                     # pid | derived | tap | none | local
    source: str
    pid: int | None = None        # set when kind == "pid"


# The 19 attributes odyssey_dash.draw_cluster() reads, and where each can come
# from on a 2006 Odyssey.
DASH_SOURCES: tuple[DashField, ...] = (
    DashField("speed", "pid", "0x0D vehicle speed", 0x0D),
    DashField("rpm", "pid", "0x0C engine RPM", 0x0C),
    DashField("coolant_f", "pid", "0x05 coolant temp", 0x05),
    DashField("volts", "pid", "0x42 control module voltage", 0x42),
    DashField("fuel", "pid", "0x2F fuel tank level", 0x2F),
    DashField("outside_f", "pid", "0x46 ambient air temp", 0x46),
    DashField("oil_psi", "none", "no sender on this engine - use 0x0B MAP, or fit a sender"),
    DashField("avg_mpg", "derived", "integrate 0x10 MAF (or 0x5E fuel rate) against 0x0D"),
    DashField("dte", "derived", "fuel level x rolling mpg"),
    DashField("odo", "derived", "integrate 0x0D over time, persist to disk"),
    DashField("trip_a", "derived", "integrate 0x0D over time"),
    DashField("trip_b", "derived", "integrate 0x0D over time"),
    DashField("lever", "tap", "gear selector - not standard OBD-II"),
    DashField("turn_left", "tap", "opto-isolated 12V tap"),
    DashField("turn_right", "tap", "opto-isolated 12V tap"),
    DashField("cruise_on", "tap", "opto-isolated 12V tap"),
    DashField("vcm_active", "tap", "Honda-specific; check obdb.community"),
    DashField("lamp_test", "local", "UI only"),
    DashField("lamp_state()", "tap", "MIL from mode 03; the rest need 12V taps"),
)


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


class ElmError(RuntimeError):
    pass


class SerialElm:
    """Minimal ELM327 client. Raw AT/hex so nothing is hidden behind a wrapper."""

    def __init__(self, port: str, baud: int, timeout: float = 5.0) -> None:
        if serial is None:
            raise ElmError("pyserial is not installed (pip install pyserial)")
        self.port_name = port
        self.baud = baud
        self.timeout = timeout
        self.ser = serial.Serial(port, baud, timeout=0.1)
        time.sleep(0.2)
        self.ser.reset_input_buffer()

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def ask(self, cmd: str, timeout: float | None = None) -> list[str]:
        """Send a command, read until the '>' prompt, return response lines."""
        limit = self.timeout if timeout is None else timeout
        self.ser.reset_input_buffer()
        self.ser.write((cmd + "\r").encode("ascii"))
        self.ser.flush()

        buf = bytearray()
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            chunk = self.ser.read(256)
            if chunk:
                buf += chunk
                if PROMPT in buf:
                    break
            elif buf:
                time.sleep(0.002)
        text = buf.replace(b"\r", b"\n").decode("ascii", "replace")
        return [ln.strip() for ln in text.replace(">", "").split("\n") if ln.strip()]


class MockElm:
    """Simulated 2006 Honda on ISO 9141-2, for testing with no hardware.

    Latency is drawn from the range a real ELM327 shows on a 10.4 kbaud
    K-line, so the throughput numbers this tool prints in --mock mode are
    representative rather than instant.
    """

    LATENCY_RANGE = (0.060, 0.110)

    VALUES = {
        0x01: bytes([0x00, 0x07, 0x00, 0x00]),   # MIL off, 0 DTCs
        0x04: bytes([0x3A]),
        0x05: bytes([0x84]),                 # 92 C, warmed up
        0x0B: bytes([0x22]),                 # 34 kPa
        0x0C: bytes([0x1B, 0x58]),           # 1750 rpm
        0x0D: bytes([0x63]),                 # 99 km/h
        0x0F: bytes([0x3C]),
        0x10: bytes([0x0B, 0xB8]),           # 30.0 g/s
        0x11: bytes([0x2E]),
        0x1F: bytes([0x05, 0xDC]),
        0x2F: bytes([0xD5]),                 # ~83 %
        0x42: bytes([0x37, 0x74]),           # 14.196 V
        0x43: bytes([0x00, 0x5A]),
    }

    # Declared in the support bitmask but never answered. Real ECUs do this,
    # and the report should call it out rather than quietly trusting either side.
    SILENT = {0x33}

    def __init__(self) -> None:
        self.port_name = "mock"
        self.baud = 38400
        self._searched = False

    @classmethod
    def _support_mask(cls, base: int) -> int | None:
        """Derive the bitmask from what this mock can actually answer."""
        declared = set(cls.VALUES) | cls.SILENT
        mask = 0
        for i in range(32):
            if base + i + 1 in declared:
                mask |= 1 << (31 - i)
        if any(p > base + 0x20 for p in declared):
            mask |= 1                        # bit 0 advertises the next range
        return mask or None

    def close(self) -> None:
        pass

    def ask(self, cmd: str, timeout: float | None = None) -> list[str]:
        cmd = cmd.replace(" ", "").upper()
        if cmd.startswith("AT"):
            time.sleep(0.01)
            return self._at(cmd)

        time.sleep(random.uniform(*self.LATENCY_RANGE))
        mode, pid = cmd[:2], int(cmd[2:4], 16)
        if mode != "01":
            return ["NO DATA"]

        prefix = [] if self._searched else ["SEARCHING..."]
        self._searched = True

        if pid in (0x00, 0x20, 0x40, 0x60):
            mask = self._support_mask(pid)
            if mask is None:
                return prefix + ["NO DATA"]
            return prefix + [f"41{pid:02X}{mask:08X}"]
        if pid in self.SILENT:
            return prefix + ["NO DATA"]
        if pid in self.VALUES:
            return prefix + [f"41{pid:02X}{self.VALUES[pid].hex().upper()}"]
        return prefix + ["NO DATA"]

    @staticmethod
    def _at(cmd: str) -> list[str]:
        table = {
            "ATZ": ["ELM327 v1.5"],
            "ATI": ["ELM327 v1.5"],
            "ATE0": ["OK"],
            "ATL0": ["OK"],
            "ATS0": ["OK"],
            "ATH0": ["OK"],
            "ATSP0": ["OK"],
            "ATDP": ["ISO 9141-2"],
            "ATDPN": ["A3"],
            "ATRV": ["14.1V"],
        }
        return table.get(cmd, ["OK"])


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def candidate_ports() -> list[str]:
    if list_ports is None:
        return []
    keep = []
    for p in list_ports.comports():
        hay = f"{p.device} {p.description} {p.hwid}".lower()
        if any(tag in hay for tag in ("usb", "ftdi", "ch340", "ch341", "prolific", "elm", "obd")):
            keep.append(p.device)
    return keep or [p.device for p in list_ports.comports()]


def connect(port: str | None, baud: int | None) -> SerialElm:
    ports = [port] if port else candidate_ports()
    if not ports:
        raise ElmError(
            "No serial ports found. Plug in the ELM327 and check it appears "
            "as /dev/ttyUSB* (run with --list-ports), or use --mock."
        )
    bauds = [baud] if baud else list(BAUD_CANDIDATES)
    last = ""
    for p in ports:
        for b in bauds:
            try:
                elm = SerialElm(p, b)
            except Exception as exc:
                last = f"{p}@{b}: {exc}"
                continue
            reply = " ".join(elm.ask("ATZ", timeout=3.0))
            if "ELM" in reply.upper():
                print(f"Connected: {p} @ {b} baud  ->  {reply}")
                return elm
            last = f"{p}@{b}: unexpected reply {reply!r}"
            elm.close()
    raise ElmError(f"Could not talk to an ELM327. Last attempt: {last}")


def init_adapter(elm) -> dict:
    for cmd in ("ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP0"):
        elm.ask(cmd, timeout=3.0)
        time.sleep(0.05)

    # First real request forces protocol negotiation; allow extra time.
    elm.ask("0100", timeout=12.0)

    info = {
        "adapter": " ".join(elm.ask("ATI")),
        "protocol": " ".join(elm.ask("ATDP")),
        "protocol_num": " ".join(elm.ask("ATDPN")),
        "adapter_voltage": " ".join(elm.ask("ATRV")),
        "port": elm.port_name,
        "baud": elm.baud,
    }
    return info


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

BAD_REPLIES = ("NO DATA", "?", "STOPPED", "UNABLE TO CONNECT", "BUS INIT", "CAN ERROR", "ERROR")


def parse_payload(lines: list[str], pid: int) -> bytes | None:
    """Pull the data bytes out of a mode-01 reply, or None if it failed."""
    want = f"41{pid:02X}"
    for ln in lines:
        clean = ln.replace(" ", "").upper()
        if any(bad in ln.upper() for bad in BAD_REPLIES):
            continue
        if clean.startswith(want):
            hexbody = clean[len(want):]
            if len(hexbody) % 2:
                hexbody = hexbody[:-1]
            try:
                return bytes.fromhex(hexbody)
            except ValueError:
                return None
    return None


def scan_supported(elm) -> set[int]:
    """Read the supported-PID bitmasks (0100 / 0120 / 0140 / 0160)."""
    supported: set[int] = set()
    for base in (0x00, 0x20, 0x40, 0x60):
        payload = parse_payload(elm.ask(f"01{base:02X}"), base)
        if not payload or len(payload) < 4:
            break
        bits = int.from_bytes(payload[:4], "big")
        for i in range(32):
            if bits & (1 << (31 - i)):
                supported.add(base + i + 1)
        if not (bits & 1):        # bit 0 == "next range supported"
            break
    return supported


@dataclass
class Reading:
    pid: Pid
    supported_flag: bool
    ok: bool = False
    value: float | None = None
    latency_ms: float = 0.0
    raw: str = ""

    def render(self) -> str:
        if not self.ok:
            return "--"
        assert self.value is not None
        if self.pid.also_f:
            return f"{self.value:.0f} {self.pid.unit} ({_c_to_f(self.value):.0f} F)"
        precision = 2 if abs(self.value) < 10 else 1 if abs(self.value) < 100 else 0
        return f"{self.value:.{precision}f} {self.pid.unit}"


def read_all(elm, supported: set[int]) -> list[Reading]:
    out = []
    for pid in PROJECT_PIDS:
        r = Reading(pid=pid, supported_flag=pid.pid in supported)
        t0 = time.monotonic()
        lines = elm.ask(pid.cmd)
        r.latency_ms = (time.monotonic() - t0) * 1000.0
        r.raw = " | ".join(lines)
        payload = parse_payload(lines, pid.pid)
        if payload:
            try:
                r.value = float(pid.decode(payload))
                r.ok = True
            except (IndexError, ValueError, ZeroDivisionError):
                r.ok = False
        out.append(r)
    return out


def throughput_single(elm, pid: Pid, seconds: float) -> dict:
    lat, ok, fail = [], 0, 0
    start = time.monotonic()
    end = start + seconds
    while time.monotonic() < end:
        t0 = time.monotonic()
        lines = elm.ask(pid.cmd)
        lat.append((time.monotonic() - t0) * 1000.0)
        if parse_payload(lines, pid.pid):
            ok += 1
        else:
            fail += 1
    total = ok + fail
    elapsed = max(time.monotonic() - start, 1e-9)
    return {
        "pid": f"0x{pid.pid:02X}",
        "name": pid.name,
        "requests": total,
        "ok": ok,
        "failed": fail,
        "rate_hz": round(total / elapsed, 2),
        "latency_ms_p50": round(statistics.median(lat), 1) if lat else 0.0,
        "latency_ms_p95": round(sorted(lat)[int(len(lat) * 0.95) - 1], 1) if len(lat) > 1 else 0.0,
        "latency_ms_max": round(max(lat), 1) if lat else 0.0,
    }


def build_schedule(answering: set[int]) -> list[int]:
    """A realistic dash polling pattern: fast values often, slow ones rarely.

    Built from PIDs that actually returned data, not from the ECU's declared
    bitmask -- the two disagree often enough that trusting the bitmask drops
    working signals.
    """
    fast = [p for p in (0x0C, 0x0D) if p in answering]
    med = [p for p in (0x04, 0x11, 0x05, 0x42) if p in answering]
    slow = [p for p in (0x2F, 0x46, 0x10) if p in answering]
    if not fast:
        return med + slow
    pattern: list[int] = []
    slots = med + slow
    for i in range(len(slots) or 1):
        pattern += fast * 2
        if slots:
            pattern.append(slots[i])
    return pattern or fast


def throughput_mix(elm, schedule: list[int], seconds: float) -> dict:
    counts: dict[int, int] = {p: 0 for p in schedule}
    lat: list[float] = []
    i = 0
    start = time.monotonic()
    end = start + seconds
    while time.monotonic() < end and schedule:
        pid_num = schedule[i % len(schedule)]
        i += 1
        pid = PID_BY_NUM[pid_num]
        t0 = time.monotonic()
        elm.ask(pid.cmd)
        lat.append((time.monotonic() - t0) * 1000.0)
        counts[pid_num] += 1
    elapsed = max(time.monotonic() - start, 1e-9)
    per_pid = {
        f"0x{p:02X}": {
            "name": PID_BY_NUM[p].name,
            "updates": n,
            "hz": round(n / elapsed, 2),
            "avg_gap_ms": round(elapsed * 1000.0 / n, 0) if n else None,
        }
        for p, n in counts.items()
    }
    return {
        "pattern": [f"0x{p:02X}" for p in schedule],
        "seconds": round(elapsed, 2),
        "total_requests": len(lat),
        "requests_per_sec": round(len(lat) / elapsed, 2),
        "latency_ms_p50": round(statistics.median(lat), 1) if lat else 0.0,
        "per_pid": per_pid,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

RULE = "-" * 78


def header(title: str) -> None:
    print(f"\n{title}\n{RULE}")


def print_report(info: dict, supported: set[int], readings: list[Reading],
                 single: dict, mix: dict) -> None:
    header("ADAPTER / BUS")
    for key in ("port", "baud", "adapter", "protocol", "protocol_num", "adapter_voltage"):
        print(f"  {key:<16} {info.get(key, '')}")
    print(f"  {'supported PIDs':<16} {len(supported)} reported by the ECU")

    header("SIGNALS THIS DASH WANTS")
    print(f"  {'PID':<6} {'SIGNAL':<26} {'VALUE':<22} {'ms':>6}  DASH FIELD")
    for r in readings:
        if r.ok:
            flag = "" if r.supported_flag else "  (works, undeclared)"
        else:
            flag = "  (declared, no data)" if r.supported_flag else "  (not supported)"
        print(
            f"  0x{r.pid.pid:02X}   {r.pid.name:<26} {r.render():<22} "
            f"{r.latency_ms:6.0f}  {r.pid.dash_field}{flag}"
        )
    notes = [(r.pid.pid, r.pid.note) for r in readings if r.pid.note]
    if notes:
        print("\n  notes:")
        for pid, note in notes:
            print(f"    0x{pid:02X}  {note}")

    undeclared = [r for r in readings if r.ok and not r.supported_flag]
    hollow = [r for r in readings if not r.ok and r.supported_flag]
    if undeclared or hollow:
        print("\n  bitmask vs. reality:")
        for r in undeclared:
            print(f"    0x{r.pid.pid:02X}  answers but is not in the support bitmask - usable")
        for r in hollow:
            print(f"    0x{r.pid.pid:02X}  declared supported but returned no data - do not rely on it")

    header("MAX RATE, SINGLE PID")
    print(f"  {single['name']} ({single['pid']})")
    print(f"    {single['rate_hz']} req/s over {single['requests']} requests "
          f"({single['failed']} failed)")
    print(f"    latency p50 {single['latency_ms_p50']} ms   "
          f"p95 {single['latency_ms_p95']} ms   max {single['latency_ms_max']} ms")

    header("REALISTIC POLLING MIX")
    print(f"  pattern: {' '.join(mix['pattern'])}")
    print(f"  {mix['requests_per_sec']} req/s total over {mix['seconds']} s "
          f"({mix['total_requests']} requests)")
    print(f"\n  {'PID':<6} {'SIGNAL':<26} {'UPDATE Hz':>10} {'AVG GAP ms':>11}")
    for pid_hex, d in mix["per_pid"].items():
        print(f"  {pid_hex:<6} {d['name']:<26} {d['hz']:>10} {str(d['avg_gap_ms']):>11}")

    rpm = mix["per_pid"].get("0x0C")
    if rpm and rpm["hz"]:
        header("WHAT THIS MEANS FOR THE DASH")
        print(f"  Tachometer updates at ~{rpm['hz']:.1f} Hz against a 60 fps render loop,")
        print(f"  so roughly {60 / rpm['hz']:.0f} frames per fresh sample. Interpolate between")
        print("  samples (odyssey_dash.ease) or the bar graph will visibly step.")
        if rpm["hz"] < 5:
            print("\n  This is slow. Consider dropping medium/slow PIDs from the loop,")
            print("  or check whether the van has an F-CAN bus you can passively sniff.")

    header("DASHBOARD FIELD READINESS")
    kinds = {"pid": "OBD-II PID", "derived": "computed", "tap": "needs 12V tap / CAN",
             "none": "unavailable", "local": "UI only"}
    pid_ok = {r.pid.pid: r.ok for r in readings}
    marks = {"derived": "+", "local": "+", "tap": "~", "none": "x"}
    for f in DASH_SOURCES:
        if f.kind == "pid":
            mark = "+" if pid_ok.get(f.pid) else "!"
        else:
            mark = marks[f.kind]
        print(f"  {mark} {f.name:<14} {kinds[f.kind]:<20} {f.source}")
    print("\n  + available    ~ needs extra wiring    ! expected but no data    x not possible")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="serial port, e.g. /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, help="baud rate (default: try 38400/9600/115200/500000)")
    ap.add_argument("--duration", type=float, default=8.0, help="seconds per throughput test")
    ap.add_argument("--json", metavar="PATH", help="also write the raw report as JSON")
    ap.add_argument("--list-ports", action="store_true", help="list serial ports and exit")
    ap.add_argument("--mock", action="store_true", help="simulate a 2006 Honda, no hardware needed")
    args = ap.parse_args(argv)

    if args.list_ports:
        if list_ports is None:
            print("pyserial not installed (pip install pyserial)")
            return 1
        ports = list(list_ports.comports())
        if not ports:
            print("No serial ports found.")
        for p in ports:
            print(f"  {p.device:<20} {p.description}  [{p.hwid}]")
        return 0

    try:
        elm = MockElm() if args.mock else connect(args.port, args.baud)
    except ElmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.mock:
        print("MOCK MODE - simulated 2006 Honda on ISO 9141-2, no vehicle attached.")

    try:
        info = init_adapter(elm)
        supported = scan_supported(elm)
        readings = read_all(elm, supported)

        answering = {r.pid.pid for r in readings if r.ok}
        hot = PID_BY_NUM[0x0C] if 0x0C in answering else next(
            (r.pid for r in readings if r.ok), PROJECT_PIDS[0]
        )
        single = throughput_single(elm, hot, args.duration)
        mix = throughput_mix(elm, build_schedule(answering), args.duration)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    finally:
        elm.close()

    print_report(info, supported, readings, single, mix)

    if args.json:
        blob = {
            "adapter": info,
            "supported_pids": sorted(f"0x{p:02X}" for p in supported),
            "readings": [
                {
                    "pid": f"0x{r.pid.pid:02X}",
                    "name": r.pid.name,
                    "supported_flag": r.supported_flag,
                    "ok": r.ok,
                    "value": r.value,
                    "unit": r.pid.unit,
                    "latency_ms": round(r.latency_ms, 1),
                    "raw": r.raw,
                }
                for r in readings
            ],
            "throughput_single": single,
            "throughput_mix": mix,
        }
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(blob, fh, indent=2)
        print(f"\nwrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
