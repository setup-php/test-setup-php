"""Read-only image inventory: no PHP setup, cache restore, or package changes."""

import csv
import datetime
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


TARGETS = {
    "librabbitmq.so.4": ("amqp", "librabbitmq4"),
    "libqdbm.so.14": ("dba", "libqdbm14"),
    "libenchant-2.so.2": ("enchant", "libenchant-2-2"),
    "libmemcached.so.11": ("memcached", "libmemcached11"),
    "libsybdb.so.5": ("pdo_dblib", "libsybdb5"),
    "libfbclient.so.2": ("pdo_firebird", "libfbclient2"),
    "libaspell.so.15": ("pspell", "libaspell15"),
    "libnetsnmp.so.40": ("snmp", "libsnmp40"),
    "libtidy.so.5deb1": ("tidy", "libtidy5deb1"),
    "libzmq.so.5": ("zmq", "libzmq5"),
    "libzip.so.4": ("zip", "libzip4"),
}


def command(args, timeout=30):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"command": args, "status": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": args, "status": -1, "stdout": "", "stderr": str(error)}


out = Path("reports")
out.mkdir(exist_ok=True)
os_release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines()
                  if "=" in line)
os_release = {key: value.strip('"') for key, value in os_release.items()}
packages = command(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${Architecture}\t${Status}\n"])
ldconfig = command([shutil.which("ldconfig") or "/sbin/ldconfig", "-p"])
(out / "dpkg-query.txt").write_text(packages["stdout"] + packages["stderr"])
(out / "ldconfig.txt").write_text(ldconfig["stdout"] + ldconfig["stderr"])
installed = {}
for line in packages["stdout"].splitlines():
    fields = line.split("\t")
    if len(fields) == 4 and fields[3] == "install ok installed":
        installed[fields[0]] = {"version": fields[1], "architecture": fields[2]}
libraries = {}
for line in ldconfig["stdout"].splitlines():
    match = re.match(r"\s*(\S+)\s+\(([^)]+)\)\s+=>\s+(\S+)", line)
    if match:
        soname, abi, path = match.groups()
        libraries.setdefault(soname, []).append({"abi": abi, "path": path,
                                                 "exists": Path(path).is_file()})

focused = {}
for soname, (extension, package) in TARGETS.items():
    probe = command([sys.executable, "-c", "import ctypes,sys; ctypes.CDLL(sys.argv[1]); print('loaded')", soname])
    matches = {name: data for name, data in installed.items()
               if name.split(":")[0] in (package, package + "t64")}
    focused[soname] = {"extension": extension, "expected_package": package,
                      "packages": matches, "ldconfig": libraries.get(soname, []),
                      "loadable": probe["status"] == 0, "probe": probe}

report = {
    "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "runner_label": os.environ["TEST_RUNNER_LABEL"],
    "environment": {name: os.environ.get(name) for name in (
        "RUNNER_ENVIRONMENT", "RUNNER_OS", "RUNNER_ARCH", "RUNNER_NAME", "ImageOS", "ImageVersion")},
    "os_release": os_release,
    "machine": platform.machine(),
    "kernel": platform.release(),
    "dpkg_architecture": command(["dpkg", "--print-architecture"]),
    "dpkg_audit": command(["dpkg", "--audit"]),
    "inventory_status": {"packages": packages["status"], "ldconfig": ldconfig["status"]},
    "installed_packages": installed,
    "shared_libraries": libraries,
    "focused_libraries": focused,
    "shtool": {"path": shutil.which("shtool"), "usr_bin_exists": Path("/usr/bin/shtool").is_file(),
               "package": installed.get("shtool")},
    "image_files": {},
}
for filename in ("/etc/image-id", "/imagegeneration/imagedata.json"):
    path = Path(filename)
    if path.is_file():
        report["image_files"][filename] = path.read_text(errors="replace")
(out / "baseline.json").write_text(json.dumps(report, indent=2) + "\n")
with (out / "focused-libraries.csv").open("w") as handle:
    writer = csv.writer(handle)
    writer.writerow(["library", "extension", "loadable", "packages", "paths", "error"])
    for soname, data in focused.items():
        writer.writerow([soname, data["extension"], data["loadable"], json.dumps(data["packages"]),
                         ";".join(item["path"] for item in data["ldconfig"]), data["probe"]["stderr"].strip()])
summary = [f"### {report['runner_label']}", "", f"Ubuntu {os_release['VERSION_ID']}, {report['machine']}", "",
           "| Library | Loadable | Installed packages |", "|---|---|---|"]
for soname, data in focused.items():
    summary.append(f"| `{soname}` | {'yes' if data['loadable'] else 'no'} | {', '.join(data['packages']) or 'absent'} |")
summary += ["", f"shtool: {report['shtool']['path'] or 'absent'}", "",
            f"Installed packages: {len(installed)}; shared-library SONAMEs: {len(libraries)}", ""]
text = "\n".join(summary)
print(text)
Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(text)
# Absent libraries are observations, not collection failures.
if packages["status"] or ldconfig["status"]:
    sys.exit(1)
