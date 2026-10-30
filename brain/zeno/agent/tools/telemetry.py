"""System telemetry: health, temperatures and processes, read through psutil.

Every read runs in a worker thread, so sampling CPU use never blocks the event loop.
``ps`` replaces the psutil module in tests.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any, Literal

import psutil
from pydantic import Field

from zeno.agent.tools.base import Risk, Tool, ToolArgs, tool


class HealthArgs(ToolArgs):
    pass


class TemperatureArgs(ToolArgs):
    pass


class TopArgs(ToolArgs):
    sort_by: Literal["cpu", "memory"] = "cpu"
    limit: int = Field(5, ge=1, le=20)


class ProcessArgs(ToolArgs):
    pid: int = Field(ge=0, le=4_194_304)


def telemetry_tools(*, ps: Any = psutil, sample_seconds: float = 0.5) -> list[Tool[Any]]:
    @tool(risk=Risk.READ_ONLY, timeout=5.0)
    async def system_health(args: HealthArgs) -> str:
        """Report CPU, load, memory, disks, uptime and battery of this computer."""
        return await asyncio.to_thread(_health, ps, sample_seconds)

    @tool(risk=Risk.READ_ONLY, timeout=5.0)
    async def system_temperatures(args: TemperatureArgs) -> str:
        """Report temperature sensors and fan speeds, flagging anything running hot."""
        return await asyncio.to_thread(_temperatures, ps)

    @tool(risk=Risk.READ_ONLY, timeout=10.0)
    async def top_processes(args: TopArgs) -> str:
        """List the processes using the most CPU or memory right now."""
        return await asyncio.to_thread(_top, ps, args.sort_by, args.limit, sample_seconds)

    @tool(risk=Risk.READ_ONLY, timeout=5.0)
    async def process_info(args: ProcessArgs) -> str:
        """Describe one process by its pid: owner, age, threads, memory and command."""
        return await asyncio.to_thread(_process, ps, args.pid)

    return [system_health, system_temperatures, top_processes, process_info]


def _health(ps: Any, sample: float) -> str:
    lines = [f"CPU {ps.cpu_percent(interval=sample)}% of {ps.cpu_count(logical=True)} cores"]
    if hasattr(ps, "getloadavg"):
        one, five, fifteen = ps.getloadavg()
        lines[0] += f", load {one:.2f} {five:.2f} {fifteen:.2f}"
    mem = ps.virtual_memory()
    lines.append(
        f"memory {mem.percent}% used ({_bytes(mem.available)} of {_bytes(mem.total)} free)"
    )
    swap = ps.swap_memory()
    if swap.total:
        lines.append(f"swap {swap.percent}% used ({_bytes(swap.used)} of {_bytes(swap.total)})")
    for part in ps.disk_partitions(all=False):
        if not part.fstype or "cdrom" in part.opts:  # Windows: an empty or optical drive
            continue
        try:
            usage = ps.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        lines.append(
            f"disk {part.mountpoint} {usage.percent}% used "
            f"({_bytes(usage.used)} of {_bytes(usage.total)})"
        )
    lines.append(_uptime(time.time() - ps.boot_time()))
    battery = ps.sensors_battery() if hasattr(ps, "sensors_battery") else None
    if battery is not None:
        lines.append(_battery(battery))
    return "\n".join(lines)


def _uptime(seconds: float) -> str:
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    if days:
        return f"up {days} day{'s' if days != 1 else ''} {hours} h"
    return f"up {hours} h {rest // 60} min"


def _battery(battery: Any) -> str:
    text = f"battery {battery.percent:.0f}%"
    if battery.power_plugged:
        return text + " (plugged in)"
    left = battery.secsleft
    if isinstance(left, int | float) and left > 0:
        hours, rest = divmod(int(left), 3600)
        return text + f" (on battery, {hours} h {rest // 60} min left)"
    return text + " (on battery)"


def _temperatures(ps: Any) -> str:
    lines = []
    temps = ps.sensors_temperatures() if hasattr(ps, "sensors_temperatures") else {}
    for chip, readings in sorted(temps.items()):
        for reading in readings:
            line = f"{chip} {reading.label or 'sensor'}: {reading.current:.1f} °C"
            if reading.critical and reading.current >= reading.critical:
                line += f" (CRITICAL, limit {reading.critical:g})"
            elif reading.high and reading.current >= reading.high:
                line += f" (above high {reading.high:g})"
            lines.append(line)
    fans = ps.sensors_fans() if hasattr(ps, "sensors_fans") else {}
    for chip, readings in sorted(fans.items()):
        lines += [f"{chip} {r.label or 'fan'}: {r.current} RPM" for r in readings]
    return "\n".join(lines) if lines else "No temperature sensors are readable here."


def _top(ps: Any, sort_by: str, limit: int, sample: float) -> str:
    rows: list[tuple[float, int, dict[str, Any]]] = []
    procs = list(ps.process_iter(["pid", "name", "username", "memory_info", "status"]))
    if sort_by == "cpu":
        alive = []
        for proc in procs:  # the first reading only starts each process's clock
            try:
                proc.cpu_percent(None)
                alive.append(proc)
            except (ps.NoSuchProcess, ps.AccessDenied, ps.ZombieProcess):
                continue
        time.sleep(sample)
        procs = alive
    for proc in procs:
        info = proc.info
        rss = info["memory_info"].rss if info.get("memory_info") else 0
        try:
            cpu = proc.cpu_percent(None) if sort_by == "cpu" else 0.0
        except (ps.NoSuchProcess, ps.AccessDenied, ps.ZombieProcess):
            continue
        rows.append((cpu if sort_by == "cpu" else float(rss), rss, {**info, "cpu": cpu}))
    rows.sort(key=lambda row: row[0], reverse=True)
    lines = [f"Top {limit} by {sort_by}: pid name user cpu memory status"]
    for _, rss, info in rows[:limit]:
        lines.append(
            f"{info['pid']} {info.get('name') or '?'} {info.get('username') or '?'} "
            f"{info['cpu']:.1f}% {_bytes(rss)} {info.get('status') or '?'}"
        )
    return "\n".join(lines)


def _process(ps: Any, pid: int) -> str:
    try:
        proc = ps.Process(pid)
        with proc.oneshot():
            name = proc.name()
            user = _safe(ps, proc.username, "unknown")
            started = datetime.fromtimestamp(proc.create_time(), UTC).astimezone()
            command = " ".join(_safe(ps, proc.cmdline, []))
            details = (
                f"{name} (pid {pid}), user {user}, {proc.status()}, "
                f"started {started.isoformat(timespec='seconds')}, "
                f"threads {proc.num_threads()}, parent {proc.ppid()}, "
                f"memory {_bytes(proc.memory_info().rss)}"
            )
    except (ps.NoSuchProcess, ps.ZombieProcess) as error:
        raise ValueError(f"no process {pid}") from error
    except ps.AccessDenied as error:
        raise ValueError(f"not allowed to read process {pid}") from error
    if len(command) > 200:
        command = command[:199] + "…"
    return f"{details}\ncommand: {command or '(not readable)'}"


def _safe(ps: Any, read: Any, default: Any) -> Any:
    try:
        return read()
    except ps.AccessDenied:
        return default


def _bytes(count: float) -> str:
    value = float(count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")
