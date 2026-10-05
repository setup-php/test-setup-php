import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as error:
        def decode(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        return {"status": 124, "command": args, "error": "Timed out after 120 seconds",
                "stdout": decode(error.stdout), "stderr": decode(error.stderr)}
    return {"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


report = {
    "environment": {key: os.environ.get(key) for key in (
        "GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "RUNNER_OS", "RUNNER_ARCH",
        "RUNNER_NAME", "ImageOS", "ImageVersion", "ACT", "CONTAINER",
    )},
    "provider_variables_present": {key: bool(os.environ.get(key)) for key in (
        "BLACKSMITH_VM_ID", "VM_ID", "BLACKSMITH_INSTALLATION_MODEL_ID",
        "BLACKSMITH_REGION", "DEPOT_ORG_ID", "DEPOT_CACHE_TOKEN",
    )},
    "provider_variable_names": sorted(key for key in os.environ if key.startswith(("BLACKSMITH_", "DEPOT_"))),
    "os_release": Path("/etc/os-release").read_text(),
    "machine": platform.machine(),
    "dpkg_architecture": command(["dpkg", "--print-architecture"]),
    "container_markers": {path: Path(path).exists() for path in ("/.dockerenv", "/run/.containerenv")},
    "container_detection": command(["systemd-detect-virt", "--container"]),
    "commands": {name: shutil.which(name) for name in ("jq", "python3", "zstd", "php", "php-config")},
    "ancestry": [],
    "runner_settings": [],
    "image_files": {},
    "dmi": {},
}

pid = os.getpid()
for _ in range(20):
    proc = Path(f"/proc/{pid}")
    try:
        executable = os.readlink(proc / "exe")
        status = (proc / "status").read_text()
        parent = next(int(line.split()[1]) for line in status.splitlines() if line.startswith("PPid:"))
    except (OSError, StopIteration) as error:
        report["ancestry"].append({"pid": pid, "error": str(error)})
        break
    report["ancestry"].append({"pid": pid, "executable": executable})
    if Path(executable).name in ("Runner.Worker", "Runner.Listener"):
        settings_path = Path(executable).parent.parent / ".runner"
        settings_report = {"path": str(settings_path), "readable": os.access(settings_path, os.R_OK)}
        try:
            settings = json.loads(settings_path.read_text())
            settings_report["keys"] = sorted(settings)
            settings_report["selected"] = {key: settings.get(key) for key in (
                "AgentName", "Ephemeral", "PoolName", "WorkFolder", "DisableUpdate",
            )}
        except (OSError, ValueError) as error:
            settings_report["error"] = str(error)
        report["runner_settings"].append(settings_report)
    if parent <= 1:
        break
    pid = parent

for filename in ("/imagegeneration/imagedata.json", "/etc/image-id", "/etc/lsb-release"):
    path = Path(filename)
    entry = {"exists": path.exists()}
    if path.is_file():
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text())
                entry["data_type"] = type(data).__name__
                if isinstance(data, list):
                    entry["groups"] = data
                entry["keys"] = sorted(data) if isinstance(data, dict) else []
                entry["selected"] = {key: data.get(key) for key in (
                    "image_os", "image_version", "ImageOS", "ImageVersion", "os", "version",
                )} if isinstance(data, dict) else {}
            except (OSError, ValueError) as error:
                entry["error"] = str(error)
        else:
            entry["text"] = path.read_text()
    report["image_files"][filename] = entry

for name in ("sys_vendor", "product_name"):
    path = Path("/sys/class/dmi/id") / name
    if path.is_file():
        report["dmi"][name] = path.read_text().strip()

report["dpkg_audit"] = command(["dpkg", "--audit"])
report["apt_check"] = command(["sudo", "-n", "apt-get", "check"])
output = json.dumps(report, indent=2)
Path("reports").mkdir(exist_ok=True)
Path("reports/runner.json").write_text(output + "\n")
print(output)
