#!/usr/bin/env python3
"""Create, validate, list, and activate portable personal-IP packages."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import zlib
from pathlib import Path
from typing import Any


STYLE_ID = "white-space-watercolor-editorial"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_HEADINGS = (
    "## 角色定位",
    "## 固定身份特征",
    "## 标志性服装与配件",
    "## 允许变化",
    "## 禁止漂移",
    "## 生图提示词片段",
    "## 一致性检查清单",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PackError(ValueError):
    """Raised for an invalid package, config, or input."""


def json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def set_private_permissions(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    try:
        if os.chmod in os.supports_follow_symlinks:
            os.chmod(path, mode, follow_symlinks=False)
        else:
            if path.is_symlink():
                raise PackError(f"Refusing to chmod symlink: {path}")
            os.chmod(path, mode)
    except OSError as exc:
        raise PackError(f"Could not set private permissions on {path}.") from exc


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    set_private_permissions(path, 0o700)


def atomic_write_text(path: Path, text: str) -> None:
    ensure_private_dir(path.parent)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        set_private_permissions(path, 0o600)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def default_home(explicit: str | None = None) -> Path:
    raw = explicit or os.environ.get("PERSONAL_IP_HOME")
    home = Path(raw).expanduser() if raw else Path.home() / ".agents" / "personal-ip-article-illustrations"
    if not home.is_absolute():
        raise PackError("Personal IP home must be an absolute path.")
    resolved = home.resolve()
    user_home = Path.home().resolve()
    skill_root = Path(__file__).resolve().parents[1]
    if resolved in (Path(resolved.anchor), user_home):
        raise PackError("Personal IP home must be a dedicated subdirectory, not a broad directory.")
    if resolved == skill_root or skill_root in resolved.parents:
        raise PackError("Personal IP data must not be stored inside the Skill repository.")
    git_root = next((candidate for candidate in (skill_root, *skill_root.parents) if (candidate / ".git").exists()), None)
    if git_root is not None:
        git_root = git_root.resolve()
        if resolved == git_root or git_root in resolved.parents:
            raise PackError("Personal IP data must not be stored inside the Skill's Git repository.")
    registry_root = skill_root.parent
    if resolved == registry_root or registry_root in resolved.parents or resolved in skill_root.parents:
        raise PackError("Personal IP data must not be stored inside or around the Skill registry.")
    return resolved


def validate_ip_id(ip_id: str) -> str:
    if not ID_PATTERN.fullmatch(ip_id):
        raise PackError("ip-id must be lowercase kebab-case using only a-z, 0-9, and hyphens.")
    return ip_id


def next_available_id(ips_root: Path, requested: str) -> str:
    validate_ip_id(requested)
    if not os.path.lexists(ips_root / requested):
        return requested
    for version in range(2, 1000):
        candidate = f"{requested}-v{version}"
        if not os.path.lexists(ips_root / candidate):
            return candidate
    raise PackError(f"No available versioned id for {requested}.")


def ensure_relative_file(pack: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise PackError(f"{label} must be a non-empty relative path.")
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise PackError(f"{label} must stay inside the package.")
    target = (pack / relative).resolve(strict=True)
    root = pack.resolve(strict=True)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PackError(f"{label} escapes the package directory.") from exc
    if not target.is_file():
        raise PackError(f"{label} does not resolve to a file.")
    return target


def image_kind(data: bytes) -> str | None:
    if data.startswith(PNG_SIGNATURE):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def strip_png_metadata(data: bytes) -> bytes:
    if not data.startswith(PNG_SIGNATURE):
        raise PackError("Expected PNG data.")
    output = bytearray(PNG_SIGNATURE)
    offset = len(PNG_SIGNATURE)
    found = set()
    keep = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"sRGB", b"gAMA", b"cHRM"}
    while offset < len(data):
        if offset + 12 > len(data):
            raise PackError("Truncated PNG chunk.")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            raise PackError("Invalid PNG chunk length.")
        chunk_type = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        stored_crc = struct.unpack(">I", data[offset + 8 + length : end])[0]
        actual_crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            raise PackError("PNG checksum validation failed.")
        if chunk_type in keep:
            output.extend(data[offset:end])
        found.add(chunk_type)
        offset = end
        if chunk_type == b"IEND":
            break
    if not {b"IHDR", b"IDAT", b"IEND"}.issubset(found):
        raise PackError("PNG is missing required chunks.")
    return bytes(output)


def normalize_turnaround(source: Path) -> bytes:
    data = source.read_bytes()
    kind = image_kind(data)
    if kind is None:
        raise PackError("Turnaround must be a valid PNG, JPEG, or WebP image.")
    try:
        from PIL import Image
    except ImportError:
        if kind != "png":
            raise PackError("Pillow is required to normalize non-PNG turnaround images.")
        return strip_png_metadata(data)

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            normalized = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            output = io.BytesIO()
            normalized.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except Exception as exc:  # Pillow raises several format-specific errors.
        raise PackError("Turnaround image cannot be decoded.") from exc


def read_character_spec(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PackError("Character spec must be UTF-8 Markdown.") from exc
    missing = [heading for heading in REQUIRED_HEADINGS if heading not in text]
    if missing:
        raise PackError("Character spec is missing headings: " + ", ".join(missing))
    if re.search(r"(?:file://|/[Uu]sers/|/[Hh]ome/|[A-Za-z]:\\)", text):
        raise PackError("Character spec must not contain source-machine absolute paths.")
    return text.rstrip() + "\n"


def validate_pack(pack: Path, require_directory_id: bool = True) -> dict[str, Any]:
    requested = pack.expanduser()
    if requested.is_symlink():
        raise PackError("The package directory itself must not be a symlink.")
    pack = requested.resolve(strict=True)
    manifest_path = pack / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PackError("manifest.json is missing or unsafe.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackError("manifest.json is not valid UTF-8 JSON.") from exc
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 1:
        raise PackError("manifest schemaVersion must be 1.")
    raw_id = manifest.get("id")
    if not isinstance(raw_id, str):
        raise PackError("manifest id must be a string.")
    ip_id = validate_ip_id(raw_id)
    if require_directory_id and pack.name != ip_id:
        raise PackError("manifest id must match the package directory name.")
    if not isinstance(manifest.get("displayName"), str) or not manifest["displayName"].strip():
        raise PackError("displayName must be a non-empty string.")
    if manifest.get("style") != STYLE_ID:
        raise PackError(f"style must be {STYLE_ID}.")
    if not isinstance(manifest.get("license"), str) or not manifest["license"].strip():
        raise PackError("license must be a non-empty string.")
    assets = manifest.get("assets")
    if not isinstance(assets, dict):
        raise PackError("assets must be an object.")
    turnaround = ensure_relative_file(pack, assets.get("turnaround"), "assets.turnaround")
    spec_path = ensure_relative_file(pack, manifest.get("characterSpec"), "characterSpec")
    turnaround_data = turnaround.read_bytes()
    if image_kind(turnaround_data) != "png":
        raise PackError("Packaged turnaround must be PNG.")
    normalized = normalize_turnaround(turnaround)
    actual_sha = hashlib.sha256(turnaround_data).hexdigest()
    if assets.get("turnaroundSha256") != actual_sha:
        raise PackError("turnaroundSha256 does not match the packaged image.")
    if not normalized.startswith(PNG_SIGNATURE):
        raise PackError("Packaged turnaround must be PNG.")
    read_character_spec(spec_path)
    return {
        "valid": True,
        "id": ip_id,
        "displayName": manifest["displayName"],
        "pack": str(pack),
        "turnaroundSha256": actual_sha,
    }


def read_config(home: Path, missing_ok: bool) -> dict[str, Any] | None:
    config_path = home / "config.json"
    if config_path.is_symlink():
        raise PackError("config.json must not be a symlink.")
    if not config_path.exists():
        if missing_ok:
            return None
        raise PackError("No active IP is configured.")
    if not config_path.is_file():
        raise PackError("config.json must be a regular file.")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackError("config.json is damaged.") from exc
    if not isinstance(config, dict) or config.get("schemaVersion") != 1:
        raise PackError("config.json has an unsupported schema.")
    active_ip = config.get("activeIp")
    if not isinstance(active_ip, str):
        raise PackError("config.json activeIp must be a string.")
    validate_ip_id(active_ip)
    return config


def installed_pack(home: Path, ip_id: str) -> Path:
    validate_ip_id(ip_id)
    ips_root = home / "ips"
    if ips_root.is_symlink():
        raise PackError("The installed ips directory must not be a symlink.")
    root = ips_root.resolve(strict=True)
    candidate = ips_root / ip_id
    if candidate.is_symlink():
        raise PackError("Installed IP package directories must not be symlinks.")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PackError("Installed IP package escapes the user data directory.") from exc
    return resolved


def activate_ip(home: Path, ip_id: str) -> dict[str, Any]:
    pack = installed_pack(home, ip_id)
    result = validate_pack(pack)
    config_path = home / "config.json"
    read_config(home, missing_ok=True)
    atomic_write_text(config_path, json_dump({"schemaVersion": 1, "activeIp": ip_id}))
    result["active"] = True
    return result


def create_pack(args: argparse.Namespace) -> dict[str, Any]:
    home = default_home(args.home)
    if args.activate:
        read_config(home, missing_ok=True)
    ips_root = home / "ips"
    if ips_root.is_symlink():
        raise PackError("The installed ips directory must not be a symlink.")
    ensure_private_dir(home)
    ensure_private_dir(ips_root)
    final_id = next_available_id(ips_root, args.id)
    target = ips_root / final_id

    turnaround_source = Path(args.turnaround).expanduser().resolve(strict=True)
    spec_source = Path(args.character_spec).expanduser().resolve(strict=True)
    turnaround_data = normalize_turnaround(turnaround_source)
    spec_text = read_character_spec(spec_source)
    turnaround_sha = hashlib.sha256(turnaround_data).hexdigest()

    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "id": final_id,
        "displayName": args.display_name.strip(),
        "style": STYLE_ID,
        "assets": {
            "turnaround": "assets/turnaround.png",
            "turnaroundSha256": turnaround_sha,
        },
        "characterSpec": "references/character-spec.md",
        "license": args.license,
    }
    if not manifest["displayName"]:
        raise PackError("display-name cannot be empty.")
    attribution = args.attribution.strip() if args.attribution else ""
    if attribution:
        manifest["attribution"] = attribution
    elif args.license != "private":
        raise PackError("Non-private packages require explicit --attribution.")

    temp_dir = Path(tempfile.mkdtemp(prefix=f".{final_id}-", dir=ips_root))
    try:
        (temp_dir / "assets").mkdir()
        (temp_dir / "references").mkdir()
        (temp_dir / "assets" / "turnaround.png").write_bytes(turnaround_data)
        (temp_dir / "references" / "character-spec.md").write_text(spec_text, encoding="utf-8")
        (temp_dir / "manifest.json").write_text(json_dump(manifest), encoding="utf-8")
        validate_pack(temp_dir, require_directory_id=False)
        try:
            target.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise PackError(f"Target {final_id} became occupied; retry the create command.") from exc
        try:
            set_private_permissions(target, 0o700)
            (target / "assets").mkdir(mode=0o700)
            (target / "references").mkdir(mode=0o700)
            set_private_permissions(target / "assets", 0o700)
            set_private_permissions(target / "references", 0o700)
            os.replace(temp_dir / "assets" / "turnaround.png", target / "assets" / "turnaround.png")
            os.replace(
                temp_dir / "references" / "character-spec.md",
                target / "references" / "character-spec.md",
            )
            os.replace(temp_dir / "manifest.json", target / "manifest.json")
            set_private_permissions(target / "assets" / "turnaround.png", 0o600)
            set_private_permissions(target / "references" / "character-spec.md", 0o600)
            set_private_permissions(target / "manifest.json", 0o600)
        except Exception:
            shutil.rmtree(target)
            raise
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    result = validate_pack(target)
    if args.activate:
        result = activate_ip(home, final_id)
    return result


def list_packs(home: Path) -> dict[str, Any]:
    config = read_config(home, missing_ok=True)
    active = config["activeIp"] if config else None

    items = []
    ips_root = home / "ips"
    if ips_root.is_symlink():
        raise PackError("The installed ips directory must not be a symlink.")
    if ips_root.is_dir():
        for manifest_path in sorted(ips_root.glob("*/manifest.json")):
            try:
                item = validate_pack(manifest_path.parent)
            except (PackError, FileNotFoundError):
                continue
            item["active"] = item["id"] == active
            items.append(item)
    return {"home": str(home), "activeIp": active, "ips": items}


def active_pack(home: Path) -> dict[str, Any]:
    config = read_config(home, missing_ok=False)
    assert config is not None
    ip_id = config["activeIp"]
    result = validate_pack(installed_pack(home, ip_id))
    result["active"] = True
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", help="Override PERSONAL_IP_HOME with an absolute path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a non-overwriting IP package")
    create.add_argument("--id", required=True, help="Lowercase kebab-case IP id")
    create.add_argument("--display-name", required=True)
    create.add_argument("--turnaround", required=True, help="Approved turnaround image, not a raw photo")
    create.add_argument("--character-spec", required=True, help="Approved UTF-8 character spec")
    create.add_argument("--license", default="private")
    create.add_argument("--attribution")
    create.add_argument("--activate", action="store_true")

    validate = subparsers.add_parser("validate", help="Validate one IP package")
    validate.add_argument("pack", type=Path)

    subparsers.add_parser("list", help="List valid installed IP packages")
    activate = subparsers.add_parser("activate", help="Activate one installed IP package")
    activate.add_argument("id")
    subparsers.add_parser("active", help="Show the active IP package")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "create":
        result = create_pack(args)
    elif args.command == "validate":
        result = validate_pack(args.pack)
    else:
        home = default_home(args.home)
        if args.command == "list":
            result = list_packs(home)
        elif args.command == "activate":
            result = activate_ip(home, args.id)
        elif args.command == "active":
            result = active_pack(home)
        else:  # pragma: no cover - argparse prevents this path.
            raise PackError("Unknown command.")
    print(json_dump(result), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PackError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
