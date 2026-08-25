from __future__ import annotations

import json
import importlib.util
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "personal-ip-article-illustrations"
IP_PACK = SKILL / "scripts" / "ip_pack.py"
LONGSHOT = SKILL / "scripts" / "build_review_longshot.py"
RELEASE_CHECK = SKILL / "scripts" / "public_release_check.py"
HEADINGS = (
    "## 角色定位",
    "## 固定身份特征",
    "## 标志性服装与配件",
    "## 允许变化",
    "## 禁止漂移",
    "## 生图提示词片段",
    "## 一致性检查清单",
)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def synthetic_png(width: int = 16, height: int = 9) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(b"\x00" + bytes([220, 210, 195]) * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) + png_chunk(b"IDAT", zlib.compress(rows)) + png_chunk(b"IEND", b"")


def run(*args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, *args], text=True, capture_output=True, env=env, check=False)
    if result.returncode != expected:
        raise AssertionError(f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


class IpPackTests(unittest.TestCase):
    def test_permission_fallback_without_follow_symlink_support(self) -> None:
        spec = importlib.util.spec_from_file_location("ip_pack_permissions_test", IP_PACK)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "private.txt"
            target.write_text("private", encoding="utf-8")
            with mock.patch.object(module.os, "supports_follow_symlinks", set()), mock.patch.object(module.os, "chmod") as chmod:
                module.set_private_permissions(target, 0o600)
                chmod.assert_called_once_with(target, 0o600)

    def test_create_validate_activate_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "user-data"
            turnaround = root / "turnaround.png"
            spec = root / "character-spec.md"
            turnaround.write_bytes(synthetic_png())
            spec.write_text("# Example\n\n" + "\n\n".join(f"{h}\n- 已确认" for h in HEADINGS) + "\n", encoding="utf-8")

            first = run(str(IP_PACK), "--home", str(home), "create", "--id", "example-ip", "--display-name", "Example", "--turnaround", str(turnaround), "--character-spec", str(spec), "--activate")
            self.assertEqual(json.loads(first.stdout)["id"], "example-ip")
            second = run(str(IP_PACK), "--home", str(home), "create", "--id", "example-ip", "--display-name", "Example", "--turnaround", str(turnaround), "--character-spec", str(spec), "--activate")
            self.assertEqual(json.loads(second.stdout)["id"], "example-ip-v2")

            active = run(str(IP_PACK), "--home", str(home), "active")
            self.assertEqual(json.loads(active.stdout)["id"], "example-ip-v2")
            validated = run(str(IP_PACK), "validate", str(home / "ips" / "example-ip"))
            self.assertTrue(json.loads(validated.stdout)["valid"])
            if os.name != "nt":
                pack = home / "ips" / "example-ip"
                self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((home / "ips").stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(pack.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((pack / "assets").stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((pack / "references").stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((pack / "manifest.json").stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE((pack / "assets" / "turnaround.png").stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE((pack / "references" / "character-spec.md").stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE((home / "config.json").stat().st_mode), 0o600)

    def test_rejects_machine_path_in_character_spec(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            turnaround = root / "turnaround.png"
            spec = root / "character-spec.md"
            turnaround.write_bytes(synthetic_png())
            forbidden = "/" + "Users" + "/someone/private-photo.png"
            spec.write_text("\n\n".join(f"{h}\n- {forbidden}" for h in HEADINGS), encoding="utf-8")
            result = run(str(IP_PACK), "--home", str(root / "data"), "create", "--id", "unsafe-ip", "--display-name", "Unsafe", "--turnaround", str(turnaround), "--character-spec", str(spec), expected=2)
            self.assertIn("absolute paths", result.stderr)

    def test_rejects_manifest_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "user-data"
            turnaround = root / "turnaround.png"
            spec = root / "character-spec.md"
            turnaround.write_bytes(synthetic_png())
            spec.write_text("# Example\n\n" + "\n\n".join(f"{h}\n- 已确认" for h in HEADINGS), encoding="utf-8")
            run(str(IP_PACK), "--home", str(home), "create", "--id", "safe-ip", "--display-name", "Safe", "--turnaround", str(turnaround), "--character-spec", str(spec))
            pack = home / "ips" / "safe-ip"
            manifest_path = pack / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["characterSpec"] = "../outside.md"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = run(str(IP_PACK), "validate", str(pack), expected=2)
            self.assertIn("must stay inside", result.stderr)

    def test_refuses_to_overwrite_damaged_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "user-data"
            turnaround = root / "turnaround.png"
            spec = root / "character-spec.md"
            turnaround.write_bytes(synthetic_png())
            spec.write_text("# Example\n\n" + "\n\n".join(f"{h}\n- 已确认" for h in HEADINGS), encoding="utf-8")
            run(str(IP_PACK), "--home", str(home), "create", "--id", "safe-ip", "--display-name", "Safe", "--turnaround", str(turnaround), "--character-spec", str(spec))
            config = home / "config.json"
            config.write_text("{not-json", encoding="utf-8")
            result = run(str(IP_PACK), "--home", str(home), "activate", "safe-ip", expected=2)
            self.assertIn("damaged", result.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), "{not-json")

    def test_create_activate_preflights_damaged_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "user-data"
            home.mkdir()
            (home / "config.json").write_text("{not-json", encoding="utf-8")
            turnaround = root / "turnaround.png"
            spec = root / "character-spec.md"
            turnaround.write_bytes(synthetic_png())
            spec.write_text("# Example\n\n" + "\n\n".join(f"{h}\n- 已确认" for h in HEADINGS), encoding="utf-8")
            result = run(str(IP_PACK), "--home", str(home), "create", "--id", "safe-ip", "--display-name", "Safe", "--turnaround", str(turnaround), "--character-spec", str(spec), "--activate", expected=2)
            self.assertIn("damaged", result.stderr)
            self.assertFalse((home / "ips" / "safe-ip").exists())

    def test_refuses_user_data_inside_git_repository(self) -> None:
        result = run(str(IP_PACK), "--home", str(REPO), "list", expected=2)
        self.assertIn("Git repository", result.stderr)

    def test_refuses_skill_registry_home_without_git(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            registry = Path(temp) / "skills"
            copied_script = registry / "personal-ip-article-illustrations" / "scripts" / "ip_pack.py"
            copied_script.parent.mkdir(parents=True)
            shutil.copy2(IP_PACK, copied_script)
            result = run(str(copied_script), "--home", str(registry), "list", expected=2)
            self.assertIn("Skill registry", result.stderr)

    def test_rejects_non_string_manifest_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "user-data"
            turnaround = root / "turnaround.png"
            spec = root / "character-spec.md"
            turnaround.write_bytes(synthetic_png())
            spec.write_text("# Example\n\n" + "\n\n".join(f"{h}\n- 已确认" for h in HEADINGS), encoding="utf-8")
            run(str(IP_PACK), "--home", str(home), "create", "--id", "safe-ip", "--display-name", "Safe", "--turnaround", str(turnaround), "--character-spec", str(spec))
            manifest_path = home / "ips" / "safe-ip" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["id"] = 123
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = run(str(IP_PACK), "validate", str(manifest_path.parent), expected=2)
            self.assertIn("must be a string", result.stderr)

    def test_non_private_license_requires_nonempty_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "user-data"
            turnaround = root / "turnaround.png"
            spec = root / "character-spec.md"
            turnaround.write_bytes(synthetic_png())
            spec.write_text("# Example\n\n" + "\n\n".join(f"{h}\n- 已确认" for h in HEADINGS), encoding="utf-8")
            result = run(str(IP_PACK), "--home", str(home), "create", "--id", "public-ip", "--display-name", "Public", "--turnaround", str(turnaround), "--character-spec", str(spec), "--license", "CC-BY-4.0", "--attribution", " ", expected=2)
            self.assertIn("require explicit", result.stderr)
            self.assertFalse((home / "ips" / "public-ip").exists())


class ReviewSheetTests(unittest.TestCase):
    def test_longshot_is_versioned(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image_a = root / "a.png"
            image_b = root / "b.png"
            Image.new("RGB", (1600, 900), "white").save(image_a)
            Image.new("RGB", (900, 1600), "white").save(image_b)
            spec = root / "review.json"
            spec.write_text(json.dumps({"title": "审片", "subtitle": "示例", "sections": [{"title": "一组", "items": [{"path": "a.png", "caption": "一"}, {"path": "b.png", "caption": "二"}]}]}, ensure_ascii=False), encoding="utf-8")
            output = root / "review.png"
            first = Path(run(str(LONGSHOT), "--spec", str(spec), "--output", str(output), "--canvas-width", "900", "--image-width", "800").stdout.strip())
            second = Path(run(str(LONGSHOT), "--spec", str(spec), "--output", str(output), "--canvas-width", "900", "--image-width", "800").stdout.strip())
            self.assertEqual(first.name, "review.png")
            self.assertEqual(second.name, "review-v2.png")
            with Image.open(first) as review:
                self.assertEqual(review.width, 900)
                self.assertGreater(review.height, 1000)


class PublicReleaseTests(unittest.TestCase):
    def test_rejects_unknown_binary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "private-article.docx").write_bytes(b"PK\x03\x04private")
            result = run(str(RELEASE_CHECK), str(root), expected=2)
            self.assertIn("unapproved", result.stderr)

    def test_rejects_windows_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            windows_path = "C:" + "\\" + "Users" + "\\someone\\private-photo.png"
            (root / "note.md").write_text(windows_path, encoding="utf-8")
            result = run(str(RELEASE_CHECK), str(root), expected=2)
            self.assertIn("machine-specific", result.stderr)


if __name__ == "__main__":
    unittest.main()
