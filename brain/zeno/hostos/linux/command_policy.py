"""The command policy: a pure, deterministic check that runs before any approval.

``check_command`` turns one line of text into an argument list (there is no shell)
and refuses, with a reason, anything in a fixed set of dangerous commands. It looks
at the parsed arguments, never at the spelling, so ``rm -rf /``, ``rm -r -f //`` and
``rm --recursive -- /etc/..`` are the same command to it. What it does not refuse
still needs the owner's approval: a denylist is a seatbelt, not a judge.
"""

import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from zeno.hostos.process import CommandRefused

TRUSTED_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin", "/usr/local/sbin")
MAX_ARGS = 64

_NAME = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
# Shell syntax that means something only to a shell, outside quotes.
_SHELL_ONLY = set("|;&<>()`$*?[")
_HINT = (
    "Commands run with no shell, so pipes, redirects, ;, &&, $variables, backticks and "
    "wildcards don't work. Run one program per call and use its own options instead."
)

# Programs that would run other code past this check: shells, interpreters,
# wrappers that start another program, privilege tools, editors and pagers that
# can spawn commands, remote shells and container runners.
_CODE_RUNNERS = re.compile(
    r"^(sh|bash|rbash|dash|zsh|ksh|mksh|csh|tcsh|fish|busybox"
    r"|(python|pypy|perl|ruby|php|lua|luajit|tclsh|wish|guile)[0-9.]*"
    r"|irb|node|nodejs|deno|bun|[gmn]?awk|julia|R|Rscript"
    r"|env|xargs|nohup|setsid|timeout|watch|nice|ionice|taskset|chrt|stdbuf|chroot"
    r"|nsenter|unshare|script|expect|flock|time|strace|ltrace|gdb|systemd-run|at|batch"
    r"|parallel|runuser|sg|newgrp|firejail|bwrap|prlimit|setpriv|capsh"
    r"|sudo|sudoedit|su|doas|pkexec|run0"
    r"|(vi|vim|nvim|view|ex|rvim|emacs)([.-].*)?|nano|pico|ed|less|more|most|man"
    r"|ssh|scp|sftp|docker|podman|nerdctl|lxc)$"
)
_DISK_TOOLS = re.compile(
    r"^(mkfs(\..+)?|mke2fs|mkswap|fdisk|sfdisk|cfdisk|parted|gdisk|sgdisk|wipefs|blkdiscard"
    r"|shred)$"
)
_POWER_TOOLS = re.compile(r"^(shutdown|reboot|poweroff|halt|init|telinit|kexec|killall5)$")
_ACCOUNT_TOOLS = re.compile(
    r"^(userdel|deluser|delgroup|groupdel|passwd|chpasswd|visudo|usermod|vipw|vigr)$"
)
_POWER_VERBS = {
    "poweroff",
    "reboot",
    "halt",
    "kexec",
    "isolate",
    "emergency",
    "rescue",
    "soft-reboot",
}
_BLOCK_DEVICE = re.compile(r"^/dev/(sd|hd|vd|xvd|nvme|mmcblk|md|dm-|loop|sr|mapper/|disk/)")
_WRITERS = {"cp", "mv", "tee", "truncate", "install", "ln", "rsync", "dd"}
_CODE_FLAGS: dict[str, tuple[set[str], set[str], set[str]]] = {
    # program: (exact tokens, long options (prefix-matched like getopt), short letters)
    "find": ({"-exec", "-execdir", "-ok", "-okdir", "-delete"}, set(), set()),
    "tar": (
        set(),
        {
            "--to-command",
            "--use-compress-program",
            "--checkpoint-action",
            "--info-script",
            "--new-volume-script",
            "--rsh-command",
        },
        {"I", "F"},
    ),
    "rsync": (set(), {"--rsh", "--rsync-path"}, {"e"}),
    "zip": ({"-TT"}, {"--unzip-command"}, set()),
}


@dataclass(frozen=True)
class PolicyContext:
    home: str
    cwd: str
    own_pid: int
    which: Callable[[str], str | None]
    """Find a program by name, searching only the trusted folders."""
    realpath: Callable[[str], str] = field(default=lambda path: path)
    """Resolve symlinks; the default only normalizes the spelling."""


@dataclass(frozen=True)
class _Args:
    shorts: set[str]
    longs: list[str]
    operands: list[str]
    tokens: list[str]

    def long(self, option: str) -> bool:
        """True if any long option is ``option`` or an unambiguous getopt abbreviation."""
        return any(_long_matches(given, option) for given in self.longs)


def check_command(text: str, ctx: PolicyContext) -> list[str]:
    """The argument list to run, with an absolute program path, or ``CommandRefused``."""
    if _CONTROL.search(text):
        raise CommandRefused("the command must be one line with no control characters")
    words = _split(text, ctx.home)
    if not words:
        raise CommandRefused("the command is empty")
    if len(words) > MAX_ARGS:
        raise CommandRefused(f"at most {MAX_ARGS} arguments are allowed")
    name, args = words[0], words[1:]
    if not _NAME.fullmatch(name):
        raise CommandRefused(
            f"run programs by their plain name (like 'ls'), not by a path such as {name!r}"
        )
    program = ctx.which(name)
    if program is None or posixpath.dirname(program) not in TRUSTED_DIRS:
        raise CommandRefused(f"{name} is not an installed system program")
    real = posixpath.basename(ctx.realpath(program))
    for alias in {name, real}:
        _check_program(alias, _parse(args), ctx)
    return [program, *args]


def _check_program(name: str, args: _Args, ctx: PolicyContext) -> None:
    if _CODE_RUNNERS.fullmatch(name):
        raise CommandRefused(
            f"{name} runs other programs or code, which would get past this check; "
            "run the program you need directly"
        )
    if name == "sed" and "--sandbox" not in args.tokens:
        raise CommandRefused("sed can run commands; use it with --sandbox")
    _check_code_flags(name, args)
    if _DISK_TOOLS.fullmatch(name):
        raise CommandRefused(f"{name} formats, partitions or wipes storage; refused")
    if _POWER_TOOLS.fullmatch(name):
        raise CommandRefused(f"{name} would shut down, restart or stop the system; refused")
    if _ACCOUNT_TOOLS.fullmatch(name):
        raise CommandRefused(f"{name} changes user accounts or passwords; refused")
    if name in {"systemctl", "loginctl"}:
        verbs = _POWER_VERBS.intersection(args.operands)
        if verbs:
            raise CommandRefused(f"{name} {min(verbs)} would stop or restart the system; refused")
    if name == "rm":
        _check_rm(args, ctx)
    if name in {"chmod", "chown", "chgrp"}:
        _check_permissions(name, args, ctx)
    if name in _WRITERS:
        _check_devices(name, args)
    if name == "kill":
        _check_kill(args.tokens, ctx)
    if name in {"pkill", "killall"}:
        _check_pkill(name, args)
    if name.startswith(("iptables", "ip6tables")) and ("F" in args.shorts or args.long("--flush")):
        raise CommandRefused(f"{name} --flush would drop every firewall rule; refused")
    if name == "nft" and "flush" in args.operands and "ruleset" in args.operands:
        raise CommandRefused("nft flush ruleset would drop every firewall rule; refused")
    if name == "ufw" and {"disable", "reset"}.intersection(args.operands):
        raise CommandRefused("turning the firewall off or resetting it is refused")
    if name == "crontab" and "r" in args.shorts:
        raise CommandRefused("crontab -r deletes every scheduled job; refused")


def _check_code_flags(name: str, args: _Args) -> None:
    if name == "git":
        _check_git(args.tokens)
        return
    exact, longs, shorts = _CODE_FLAGS.get(name, (set(), set(), set()))
    letters = set(args.shorts)
    if name == "tar" and args.tokens and not args.tokens[0].startswith("-"):
        letters.update(args.tokens[0])  # old-style "tar xIf ...": the first word is flags
    found = exact.intersection(args.tokens) or {o for o in longs if args.long(o)}
    found |= {f"-{s}" for s in shorts & letters}
    if found:
        raise CommandRefused(f"{name} {min(found)} runs another program; refused")


def _check_git(tokens: list[str]) -> None:
    # Checked anywhere, not only before the subcommand: "git -C dir -c x=y log" would
    # otherwise hide -c behind the folder argument. (So "git log -c" is refused too.)
    for word in tokens:
        if (
            word == "-c"
            or word.startswith("ext::")
            or any(
                _long_matches(word, option)
                for option in (
                    "--config-env",
                    "--exec-path",
                    "--upload-pack",
                    "--receive-pack",
                    "--exec",
                )
            )
        ):
            raise CommandRefused(f"git {word} can run another program; refused")
    fetching = {"clone", "fetch", "pull", "ls-remote", "archive"}.intersection(tokens)
    if fetching and "-u" in tokens:
        raise CommandRefused("git -u (--upload-pack) runs another program; refused")


def _check_rm(args: _Args, ctx: PolicyContext) -> None:
    if args.long("--no-preserve-root"):
        raise CommandRefused("rm --no-preserve-root is refused")
    if not ({"r", "R"} & args.shorts or args.long("--recursive")):
        return
    for operand in args.operands:
        if _protected(operand, ctx):
            raise CommandRefused(
                f"rm -r on {operand} would delete the system or your home folder; refused"
            )


def _check_permissions(name: str, args: _Args, ctx: PolicyContext) -> None:
    targets = [o for o in args.operands if _protected(o, ctx)]
    if not targets:
        return
    if {"R"} & args.shorts or args.long("--recursive"):
        raise CommandRefused(f"{name} -R on {targets[0]} would change the whole system; refused")
    modes = args.operands + [f"-{s}" for s in args.shorts]
    if name == "chmod" and any(_world_writable(m) for m in modes):
        raise CommandRefused(f"making {targets[0]} writable by everyone is refused")


def _world_writable(mode: str) -> bool:
    if re.fullmatch(r"0?[0-7]{3,4}", mode):
        return mode[-1] in "2367"
    for clause in mode.split(","):
        match = re.fullmatch(r"([ugoa]*)([-+=])([rwxXst]*)", clause)
        if (
            match
            and match[2] in "+="
            and "w" in match[3]
            and (not match[1] or set(match[1]) & set("oa"))
        ):
            return True
    return False


def _check_devices(name: str, args: _Args) -> None:
    for word in args.tokens:
        path = word.removeprefix("of=") if name == "dd" else word
        if name == "dd" and not word.startswith("of="):
            continue
        if _BLOCK_DEVICE.match(posixpath.normpath(path)):
            raise CommandRefused(f"{name} would write straight onto the disk {path}; refused")


def _check_kill(tokens: list[str], ctx: PolicyContext) -> None:
    targets: list[str] = []
    i = 0
    while i < len(tokens):
        word = tokens[i]
        if word == "--":
            targets += tokens[i + 1 :]
            break
        if word in {"-s", "-n", "--signal"}:
            i += 2
            continue
        if word.startswith("-") and i == 0:
            i += 1  # the signal, like -9 or -HUP
            continue
        targets.append(word)
        i += 1
    if {"1", "-1", str(ctx.own_pid)} & set(targets):
        raise CommandRefused("killing init, every process or Zeno itself is refused")


def _check_pkill(name: str, args: _Args) -> None:
    if "u" in args.shorts or args.long("--user"):
        raise CommandRefused(f"{name} by user would also stop Zeno; name the process instead")
    for pattern in args.operands:
        low = pattern.lower()
        if low in {"systemd", "init"} or "zeno" in low or low.startswith("python"):
            raise CommandRefused(f"{name} {pattern} would stop the system or Zeno; refused")


def _protected(operand: str, ctx: PolicyContext) -> bool:
    """The root, a top-level folder, the home folder or one of its parents."""
    path = _normalize(posixpath.join(ctx.cwd, operand))
    for candidate in {path, _normalize(ctx.realpath(path))}:
        home = _normalize(ctx.home)
        if candidate.count("/") <= 1 or candidate == home or home.startswith(candidate + "/"):
            return True
    return False


def _normalize(path: str) -> str:
    normal = posixpath.normpath(path)
    return "/" + normal.lstrip("/") if normal.startswith("/") else normal


def _long_matches(given: str, option: str) -> bool:
    name = given.split("=", 1)[0]
    return name.startswith("--") and len(name) > 3 and option.startswith(name)


def _parse(tokens: list[str]) -> _Args:
    shorts: set[str] = set()
    longs: list[str] = []
    operands: list[str] = []
    options_done = False
    for word in tokens:
        if options_done or word == "-" or not word.startswith("-"):
            operands.append(word)
        elif word == "--":
            options_done = True
        elif word.startswith("--"):
            longs.append(word)
        else:
            shorts.update(word[1:])
    return _Args(shorts, longs, operands, tokens)


def _split(text: str, home: str) -> list[str]:
    """Split like a POSIX shell would, but refuse anything only a shell understands."""
    words: list[str] = []
    current: list[str] = []
    in_word = False
    quote = ""
    i = 0
    while i < len(text):
        char = text[i]
        if quote == "'":
            if char == "'":
                quote = ""
            else:
                current.append(char)
        elif quote == '"':
            if char == '"':
                quote = ""
            elif char in "$`":
                raise CommandRefused(_HINT)
            elif char == "\\" and i + 1 < len(text) and text[i + 1] in '"\\$`':
                i += 1
                current.append(text[i])
            else:
                current.append(char)
        elif char in " \t":
            if in_word:
                words.append("".join(current))
                current, in_word = [], False
        elif char in "'\"":
            quote, in_word = char, True
        elif char == "\\":
            if i + 1 >= len(text):
                raise CommandRefused("the command ends with a lone backslash")
            i += 1
            current.append(text[i])
            in_word = True
        elif char in _SHELL_ONLY:
            raise CommandRefused(_HINT)
        elif char == "~" and not in_word and (i + 1 == len(text) or text[i + 1] in "/ \t"):
            current.append(home)
            in_word = True
        else:
            current.append(char)
            in_word = True
        i += 1
    if quote:
        raise CommandRefused("the command has an unclosed quote")
    if in_word:
        words.append("".join(current))
    return words
