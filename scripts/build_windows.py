#!/usr/bin/env python3
"""Cross-package pinned Windows binaries on Linux or Windows; never execute downloads on Linux."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    "LICENSE",
    "README.md",
    "USER_GUIDE.md",
    "TESTING_ON_WINDOWS.md",
    "NEXT_STEPS.md",
    "THIRD_PARTY_NOTICES.md",
    "SECURITY_REVIEW.md",
]


def download(entry):
    path = ROOT / "downloads" / entry["filename"]
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix(path.suffix + ".partial")
        request = urllib.request.Request(entry["url"], headers={"User-Agent": "VoucherReorder-build/0.1"})
        with urllib.request.urlopen(request, timeout=120) as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output)
        temporary.replace(path)
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(f"Checksum mismatch: {path.name}. Remove the cached file and investigate.")
    return path


def zip_extract(source, target):
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe archive path")
        archive.extractall(target)


def collect_notices(source, target):
    """Preserve all embedded notices, including transitive libraries and fonts."""
    with tarfile.open(source) as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not member.isfile():
                continue
            if not any(
                word in path.name.lower() for word in ("license", "licence", "copying", "copyright", "notice")
            ):
                continue
            dest = target.joinpath(*path.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as data, dest.open("wb") as output:
                shutil.copyfileobj(data, output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--version", help="Three-part packaging version override for upgrade tests")
    args = parser.parse_args()
    version = args.version or tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    import re

    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Version must be major.minor.patch")
    dependencies = json.loads((ROOT / "packaging/dependencies.json").read_text())
    files = {key: download(value) for key, value in dependencies.items()}
    stage = ROOT / "build/windows"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    zip_extract(files["python-runtime"], stage / "runtime")
    (stage / "runtime/python313._pth").write_text("python313.zip\n.\n..\n", encoding="utf-8")
    zip_extract(files["pypdf-wheel"], stage / "runtime")
    shutil.copytree(
        ROOT / "voucher_reorder", stage / "voucher_reorder", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy2(ROOT / "app.py", stage / "app.py")
    shutil.copytree(ROOT / "packaging", stage / "packaging")
    for name in DOCS:
        shutil.copy2(ROOT / name, stage / name)
    shutil.copy2(ROOT / "USER_GUIDE.md", stage / "USER_GUIDE.txt")
    (stage / "PACKAGE.json").write_text(
        json.dumps({"identity": "org.voucher-reorder.desktop", "version": version})
    )
    vendor = stage / "vendor"
    pdfium = vendor / "pdfium"
    with zipfile.ZipFile(files["pdfium-runtime"]) as archive:
        pdfium.mkdir(parents=True)
        for name in ("pdfium.dll", "version.json"):
            (pdfium / name).write_bytes(archive.read("pypdfium2_raw/" + name))
        for name in archive.namelist():
            if ".dist-info/licenses/" in name and not name.endswith("/"):
                target = pdfium / "licenses" / name.split(".dist-info/licenses/", 1)[1]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
    gs = vendor / "ghostscript"
    sevenzip = (
        shutil.which("7z")
        or shutil.which("7zz")
        or str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "7-Zip/7z.exe")
    )
    subprocess.run(
        [
            sevenzip,
            "x",
            "-y",
            str(files["ghostscript-runtime"]),
            f"-o{gs}",
            "bin/*",
            "lib/*",
            "Resource/*",
            "iccprofiles/*",
            "doc/*",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if not (gs / "bin/gswin64c.exe").exists():
        raise RuntimeError("Ghostscript extraction failed")
    notices = stage / "licenses"
    notices.mkdir()
    shutil.copy2(stage / "runtime/LICENSE.txt", notices / "Python-LICENSE.txt")
    for key in ("python-source", "pypdf-source", "ghostscript-source"):
        collect_notices(files[key], notices / key)
    # NSIS executable stubs/plugins use the zlib/libpng license. Full tool distribution
    # also includes build-time components; preserve its upstream license document.
    shutil.copy2(ROOT / "packaging/NSIS-COPYING.txt", notices / "NSIS-COPYING.txt")
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except subprocess.CalledProcessError:
        revision = "source-archive-build"
    tool_versions = {"7-Zip": subprocess.check_output([sevenzip, "i"], text=True).splitlines()[1]}
    if not args.stage_only:
        compiler = shutil.which("makensis") or str(
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "NSIS/makensis.exe"
        )
        prefix = "/" if os.name == "nt" else "-"
        tool_versions["NSIS"] = subprocess.check_output([compiler, prefix + "VERSION"], text=True).strip()
        if os.name == "nt":
            tool_versions["MSVC"] = subprocess.run(["cl"], capture_output=True, text=True).stderr.strip()
    (stage / "BUILD_INFO.json").write_text(
        json.dumps(
            {"version": version, "revision": revision, "dependencies": dependencies, "tools": tool_versions},
            indent=2,
        )
    )
    (stage / "SOURCE.txt").write_text(
        "Voucher Reorder is GPL-3.0-or-later. Ghostscript remains AGPL-3.0-or-later.\n"
        "Corresponding source and original notices accompany this installer as\n"
        f"VoucherReorder-{version}-sources.zip in the SAME Actions artifact or Release.\n"
        "https://github.com/matthew-nigh/voucher-reorder\n"
        "Keep the source archive available alongside every binary redistribution.\n"
        "See THIRD_PARTY_NOTICES.md for licenses and upstream build instructions.\n",
        encoding="utf-8",
    )
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    # Source distribution uses an explicit allowlist: no local user data, credentials, or downloads outside pins.
    with zipfile.ZipFile(
        dist / f"VoucherReorder-{version}-sources.zip", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for key, path in files.items():
            if key.endswith("-source"):
                archive.write(path, "upstream/" + path.name)
        for name in [*DOCS, "app.py", "pyproject.toml", "requirements-dev.txt", ".gitignore"]:
            archive.write(ROOT / name, "voucher-reorder/" + name)
        for directory in ["voucher_reorder", "tests", "scripts", "packaging", ".github"]:
            for path in (ROOT / directory).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, "voucher-reorder/" + path.relative_to(ROOT).as_posix())
        archive.write(stage / "BUILD_INFO.json", "BUILD_INFO.json")
    if not args.stage_only:
        if os.name == "nt":
            helper = ROOT / "build/Provision.exe"
            subprocess.run(
                [
                    "cl",
                    "/nologo",
                    "/O2",
                    "/MT",
                    "/std:c11",
                    str(ROOT / "packaging/provision.c"),
                    f"/Fe:{helper}",
                    "/link",
                    "/SUBSYSTEM:WINDOWS",
                    "shell32.lib",
                    "advapi32.lib",
                    "user32.lib",
                ],
                cwd=helper.parent,
                check=True,
            )
            subprocess.run(
                [
                    compiler,
                    f"/DHELPER={helper}",
                    f"/DVERSION={version}",
                    f"/DOUTPUT={dist / f'VoucherReorder-{version}-Provisioning.exe'}",
                    str(ROOT / "packaging/provision.nsi"),
                ],
                check=True,
            )
            provisioning = stage / "provisioning"
            provisioning.mkdir()
            package = dist / f"VoucherReorder-{version}-Provisioning.exe"
            shutil.copy2(package, provisioning / "Setup.exe")
            (provisioning / "package.json").write_text(
                json.dumps({"version": version, "sha256": hashlib.sha256(package.read_bytes()).hexdigest()})
            )
        installer = dist / f"VoucherReorder-{version}-Setup.exe"
        subprocess.run(
            [
                compiler,
                f"{prefix}DSTAGE={stage}",
                f"{prefix}DOUTPUT={installer}",
                str(ROOT / "packaging/installer.nsi"),
            ],
            check=True,
        )
    with (dist / "SHA256SUMS.txt").open("w") as output:
        for path in sorted(dist.iterdir()):
            if path.suffix in (".zip", ".exe"):
                with path.open("rb") as data:
                    output.write(f"{hashlib.file_digest(data, 'sha256').hexdigest()}  {path.name}\n")
    print(f"Windows package ready: {dist}")


if __name__ == "__main__":
    main()
