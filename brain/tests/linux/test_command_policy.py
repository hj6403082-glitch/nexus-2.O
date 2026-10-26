"""The command policy: a pure check that refuses dangerous commands before approval.

Each refused family is tested in many spellings, and a property test generates
thousands more, so the refusal does not depend on flag order, grouping, long or
short flags, ``--``, quoting or path spelling.
"""

import shlex

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zeno.hostos.linux.command_policy import CommandRefused, PolicyContext, check_command

HOME = "/home/boss"
LINKS = {"/usr/bin/sh": "/usr/bin/dash", "/usr/bin/editor": "/usr/bin/vim.basic"}


def which(name: str) -> str | None:
    if name in {"missing", "nosuch"}:
        return None
    if name == "localtool":
        return "/home/boss/bin/localtool"
    return f"/usr/bin/{name}"


def realpath(path: str) -> str:
    return LINKS.get(path, path)


CTX = PolicyContext(home=HOME, cwd=HOME, own_pid=4242, which=which, realpath=realpath)


def refused(command: str, ctx: PolicyContext = CTX) -> str:
    with pytest.raises(CommandRefused) as caught:
        check_command(command, ctx)
    return str(caught.value)


# --- what passes ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "argv"),
    [
        ("ls -la /etc", ["/usr/bin/ls", "-la", "/etc"]),
        ("df -h", ["/usr/bin/df", "-h"]),
        ("systemctl --user restart zeno", ["/usr/bin/systemctl", "--user", "restart", "zeno"]),
        ("journalctl -u nginx -n 50", ["/usr/bin/journalctl", "-u", "nginx", "-n", "50"]),
        ("rm -rf /home/boss/build", ["/usr/bin/rm", "-rf", "/home/boss/build"]),
        ("rm -rf build", ["/usr/bin/rm", "-rf", "build"]),
        ("rm /etc", ["/usr/bin/rm", "/etc"]),  # not recursive: rm refuses on its own
        ("chmod 644 notes.txt", ["/usr/bin/chmod", "644", "notes.txt"]),
        ("chmod -R u+w /home/boss/project", ["/usr/bin/chmod", "-R", "u+w", "/home/boss/project"]),
        ("echo 'a | b ; c'", ["/usr/bin/echo", "a | b ; c"]),
        ("cat ~/notes.txt", ["/usr/bin/cat", "/home/boss/notes.txt"]),
        (
            "dd if=/dev/zero of=/home/boss/blank.img bs=1M count=1",
            ["/usr/bin/dd", "if=/dev/zero", "of=/home/boss/blank.img", "bs=1M", "count=1"],
        ),
        ("kill -HUP 1234", ["/usr/bin/kill", "-HUP", "1234"]),
        ("systemctl status reboot.target", ["/usr/bin/systemctl", "status", "reboot.target"]),
        (
            "sed --sandbox -n 1,5p notes.txt",
            ["/usr/bin/sed", "--sandbox", "-n", "1,5p", "notes.txt"],
        ),
        ("git status", ["/usr/bin/git", "status"]),
        ("tar -czf backup.tgz notes", ["/usr/bin/tar", "-czf", "backup.tgz", "notes"]),
    ],
)
def test_ordinary_commands_pass_with_an_absolute_program(command: str, argv: list[str]) -> None:
    assert check_command(command, CTX) == argv


# --- shape --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "",
        "   ",
        "echo 'unterminated",
        "echo a\nrm -rf /",
        "echo \x00",
        "echo \x1b[2J",
        " ".join(["x"] * 66),
    ],
)
def test_malformed_commands_are_refused(command: str) -> None:
    refused(command)


@pytest.mark.parametrize(
    "command",
    [
        "ls | grep x",
        "ls; rm x",
        "make && make install",
        "a || b",
        "sleep 5 &",
        "echo hi > /etc/motd",
        "cat < /etc/shadow",
        "echo $(whoami)",
        "echo `id`",
        "ls *.txt",
        "ls file?.log",
        "echo $HOME",
        "echo ${PATH}",
        "ls 2>&1",
    ],
)
def test_shell_syntax_is_refused_with_a_hint(command: str) -> None:
    assert "no shell" in refused(command)


# --- the program --------------------------------------------------------------------


@pytest.mark.parametrize(
    "command", ["./deploy.sh", "/tmp/x", "../bin/ls", "bin/ls", "missing --help", "localtool"]
)
def test_programs_must_be_trusted_system_binaries(command: str) -> None:
    refused(command)


@pytest.mark.parametrize(
    "command",
    [
        "bash -c 'rm -rf /'",
        "sh -c id",
        "zsh",
        "dash",
        "busybox rm -rf /",
        "fish",
        "python3 -c 'import os'",
        "python3.12 x.py",
        "perl -e 1",
        "ruby -e 1",
        "node -e 1",
        "php -r 1",
        "lua5.4",
        "awk 'BEGIN{system(\"id\")}'",
        "gawk 1",
        "env rm -rf /",
        "xargs rm",
        "nohup rm -rf /",
        "setsid x",
        "timeout 5 rm -rf /",
        "watch ls",
        "nice rm",
        "ionice rm",
        "stdbuf -o0 ls",
        "chroot / sh",
        "nsenter -t 1",
        "unshare -r",
        "script -c id",
        "expect x",
        "flock /tmp/l rm",
        "strace ls",
        "systemd-run rm -rf /",
        "at now",
        "sudo ls",
        "su -",
        "doas ls",
        "pkexec ls",
        "run0 ls",
        "vim -c '!id'",
        "vi x",
        "nano x",
        "less x",
        "man ls",
        "ssh host",
        "scp a b",
        "docker run -v /:/h alpine",
        "podman exec x sh",
        "sed -i s/a/b/ f",
        "sed 1e\\ id f",
        "editor x",
        "sh",
    ],
)
def test_programs_that_run_other_code_are_refused(command: str) -> None:
    refused(command)


@pytest.mark.parametrize(
    "command",
    [
        "find / -name x -exec rm {} +",
        "find . -execdir id ;",
        "find . -ok rm {} ;",
        "find / -delete",
        "git -c core.pager=id log",
        "git --config-env=x=y log",
        "git clone ext::sh -c id",
        "git fetch --upload-pack=id origin",
        "tar --to-command=id -xf a.tar",
        "tar -I 'sh -c id' -xf a",
        "tar --use-compress-program=id -xf a",
        "tar --checkpoint-action=exec=id -cf a .",
        "rsync -e 'sh -c id' a b",
        "rsync --rsh=id a b",
        "rsync --rsync-path=id a b",
        "zip -TT id a.zip x",
        "git -C /tmp -c core.pager=id log",
        "git --git-dir=x -c a=b status",
        "tar xIf id a.tar",
        "tar --to-com=id -xf a.tar",
        "rsync -avessh a b",
    ],
)
def test_flags_that_run_code_are_refused(command: str) -> None:
    refused(command)


# --- catastrophic commands ----------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "rm -fr /",
        "rm -r -f /",
        "rm --recursive --force /",
        "rm -rf //",
        "rm -rf /./",
        "rm -rf -- /",
        "rm -Rf /",
        "rm -rfv /etc",
        "rm -rf /etc/..",
        "rm -rf ///",
        "rm -rf /usr/",
        "rm -rf /home",
        "rm -rf /boot",
        "rm -rf ~",
        "rm -rf ~/",
        "rm -rf /home/boss",
        "rm -rf /home/boss/..",
        "rm -rf ../..",
        "rm -rf build /",
        "rm --no-preserve-root x",
        "rm '-rf' '/'",
        "rm -r /var",
        "rm -rf /lib64",
        "rm -rf /srv",
    ],
)
def test_recursive_removal_of_the_system_or_home_is_refused(command: str) -> None:
    assert "refused" in refused(command)


@pytest.mark.parametrize(
    "command",
    [
        "chmod -R 777 /",
        "chmod --recursive a+w /etc",
        "chown -R boss /usr",
        "chgrp -R x /var",
        "chmod 777 /",
        "chmod a+w /etc",
        "chmod o+w /usr",
        "chmod +w /",
        "chmod 0777 /home",
        "chown -R nobody ~",
    ],
)
def test_permission_changes_on_the_system_are_refused(command: str) -> None:
    refused(command)


@pytest.mark.parametrize(
    "command",
    [
        "mkfs.ext4 /dev/sda1",
        "mkfs -t ext4 /dev/sdb",
        "mke2fs /dev/sdb",
        "mkswap /dev/sdb2",
        "fdisk /dev/sda",
        "sfdisk /dev/sda",
        "parted /dev/sda rm 1",
        "sgdisk -Z /dev/sda",
        "wipefs -a /dev/sda",
        "blkdiscard /dev/nvme0n1",
        "shred -u secrets.txt",
        "dd if=/dev/zero of=/dev/sda",
        "dd of=/dev/nvme0n1p1 if=x",
        "cp image.iso /dev/sdb",
        "mv x /dev/mmcblk0",
        "tee /dev/sda",
        "truncate -s 0 /dev/vda",
    ],
)
def test_disk_destruction_is_refused(command: str) -> None:
    refused(command)


@pytest.mark.parametrize(
    "command",
    [
        "shutdown now",
        "reboot",
        "poweroff",
        "halt",
        "init 0",
        "telinit 6",
        "kexec -e",
        "systemctl poweroff",
        "systemctl reboot",
        "systemctl --force halt",
        "systemctl kexec",
        "systemctl isolate rescue.target",
        "systemctl emergency",
        "systemctl rescue",
        "systemctl soft-reboot",
        "loginctl poweroff",
    ],
)
def test_power_and_boot_changes_are_refused(command: str) -> None:
    refused(command)


@pytest.mark.parametrize(
    "command",
    [
        "kill 1",
        "kill -9 1",
        "kill -s KILL 1",
        "kill -9 -1",
        "kill -- -1",
        "kill 4242",
        "pkill systemd",
        "killall init",
        "pkill -f zeno",
        "pkill python3",
        "killall5",
    ],
)
def test_killing_init_everything_or_zeno_is_refused(command: str) -> None:
    refused(command)


@pytest.mark.parametrize(
    "command",
    [
        "iptables -F",
        "iptables --flush",
        "ip6tables -F INPUT",
        "nft flush ruleset",
        "ufw disable",
        "ufw reset",
        "userdel boss",
        "deluser boss",
        "passwd",
        "chpasswd",
        "visudo",
        "usermod -L boss",
        "crontab -r",
        "crontab -ir",
    ],
)
def test_firewall_accounts_and_cron_wipes_are_refused(command: str) -> None:
    refused(command)


def test_relative_paths_are_judged_from_the_working_folder() -> None:
    at_root = PolicyContext(home=HOME, cwd="/", own_pid=1, which=which, realpath=realpath)
    refused("rm -rf etc", at_root)
    assert check_command("rm -rf etc/old", at_root)[-1] == "etc/old"


def test_symlinks_to_protected_folders_are_followed() -> None:
    links = {"/home/boss/sys": "/usr"}
    ctx = PolicyContext(
        home=HOME, cwd=HOME, own_pid=1, which=which, realpath=lambda p: links.get(p, p)
    )
    refused("rm -rf sys", ctx)


def test_a_quoted_tilde_is_a_folder_named_tilde() -> None:
    assert check_command("rm -r '~'", CTX)[-1] == "~"


def test_a_refusal_says_why() -> None:
    assert "rm" in refused("rm -rf /") and "/" in refused("rm -rf /")


# --- property tests -----------------------------------------------------------------

RECURSIVE = st.sampled_from(["-r", "-R", "--recursive"])
OTHER_RM_FLAGS = st.lists(
    st.sampled_from(["-f", "--force", "-v", "--verbose", "-I", "--one-file-system"]), max_size=3
)
PROTECTED = st.sampled_from(
    [
        "/",
        "//",
        "///",
        "/./",
        "/.",
        "/etc",
        "/etc/",
        "/etc/..",
        "/usr/../",
        "/home",
        "/home/",
        "~",
        "~/",
        HOME,
        HOME + "/",
        HOME + "/.",
        "/var",
        "/boot//",
        "/usr/./",
        "/opt",
        "/root",
        "/home/boss/../..",
        "..",
        "../..",
        "../../",
    ]
)
SAFE_TARGET = st.sampled_from(["build", "/home/boss/tmp", "~/old", "dist/", "/tmp/x"])


def spell_flags(draw: st.DrawFn, flags: list[str]) -> list[str]:
    """Spell short flags apart or grouped (-r -f or -rf), and shuffle everything."""
    shorts = [f[1] for f in flags if len(f) == 2]
    longs = [f for f in flags if len(f) > 2]
    if shorts and draw(st.booleans()):
        grouped = ["-" + "".join(draw(st.permutations(shorts)))]
    else:
        grouped = [f"-{s}" for s in shorts]
    return list(draw(st.permutations(grouped + longs)))


@st.composite
def recursive_removals(draw: st.DrawFn) -> str:
    flags = spell_flags(draw, [draw(RECURSIVE), *draw(OTHER_RM_FLAGS)])
    targets = [draw(PROTECTED), *draw(st.lists(SAFE_TARGET, max_size=2))]
    targets = list(draw(st.permutations(targets)))
    parts = flags + (["--"] if draw(st.booleans()) else []) + targets
    if draw(st.booleans()):  # options may also follow operands (GNU style)
        parts = targets + flags
    quote = draw(st.booleans())
    # Quoting "~" would make it a literal folder named "~", so only it stays bare.
    return " ".join(
        ["rm", *[shlex.quote(p) if quote and not p.startswith("~") else p for p in parts]]
    )


@settings(max_examples=3000, deadline=None)
@given(recursive_removals())
def test_every_spelling_of_recursive_removal_of_a_protected_folder_is_refused(
    command: str,
) -> None:
    at_work = PolicyContext(
        home=HOME, cwd="/home/boss/work", own_pid=1, which=which, realpath=realpath
    )
    with pytest.raises(CommandRefused):
        check_command(command, at_work)


@st.composite
def recursive_permission_changes(draw: st.DrawFn) -> str:
    program = draw(st.sampled_from(["chmod", "chown", "chgrp"]))
    mode = {"chmod": "755", "chown": "boss", "chgrp": "staff"}[program]
    flags = spell_flags(
        draw,
        [
            draw(st.sampled_from(["-R", "--recursive"])),
            *draw(st.lists(st.sampled_from(["-v", "-c", "-f"]), max_size=2)),
        ],
    )
    return " ".join([program, *flags, mode, draw(PROTECTED)])


@settings(max_examples=1000, deadline=None)
@given(recursive_permission_changes())
def test_every_spelling_of_a_recursive_permission_change_on_the_system_is_refused(
    command: str,
) -> None:
    at_work = PolicyContext(
        home=HOME, cwd="/home/boss/work", own_pid=1, which=which, realpath=realpath
    )
    with pytest.raises(CommandRefused):
        check_command(command, at_work)


@settings(max_examples=500, deadline=None)
@given(st.lists(st.sampled_from(["-r", "-f", "-v", "--force"]), max_size=3), SAFE_TARGET)
def test_removing_a_project_folder_is_left_to_the_owner(flags: list[str], target: str) -> None:
    assert check_command(" ".join(["rm", *flags, target]), CTX)[0] == "/usr/bin/rm"
