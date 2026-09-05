"""Package the extension as a .vsix, with no Node toolchain.

    python editors/vscode/build_vsix.py

WHY NOT `vsce`
--------------
`npm install -g @vscode/vsce` is the documented way and it needs Node, npm, and
a network round trip. This project's whole posture is that you can go from a
clean checkout to a working tool without any of those, and the extension itself
has no dependencies and no build step -- so requiring a package manager purely
to zip a folder would be the only npm dependency in the entire repository.

A .vsix is a ZIP with three things in it, and that is the whole format:

    [Content_Types].xml     maps file extensions to MIME types
    extension.vsixmanifest  the XML manifest VS Code reads at install time
    extension/**            the extension itself, exactly as it sits on disk

Everything else `vsce` does -- linting, README rendering, dependency bundling --
is for publishing to the Marketplace, which is not what this is for.

The output installs with:

    code --install-extension req2code-0.1.0.vsix
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "req2code"

#: Files never worth shipping. Kept small deliberately: the extension has no
#: build output and no dependencies, so almost everything in the folder is
#: meant to be there.
EXCLUDE_NAMES = frozenset({".DS_Store", "Thumbs.db", "node_modules", ".git"})

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="js" ContentType="application/javascript"/>
  <Default Extension="css" ContentType="text/css"/>
  <Default Extension="html" ContentType="text/html"/>
  <Default Extension="svg" ContentType="image/svg+xml"/>
  <Default Extension="md" ContentType="text/markdown"/>
  <Default Extension="vsixmanifest" ContentType="text/xml"/>
</Types>
"""

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{name}" Version="{version}" Publisher="{publisher}"/>
    <DisplayName>{display_name}</DisplayName>
    <Description xml:space="preserve">{description}</Description>
    <Tags>traceability,requirements,code-search</Tags>
    <Categories>Other</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{engine}"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value=""/>
      <Property Id="Microsoft.VisualStudio.Services.Links.Source" Value=""/>
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest"
           Path="extension/package.json" Addressable="true"/>
  </Assets>
</PackageManifest>
"""


def escape(text: str) -> str:
    """Minimal XML escaping. The manifest is XML and these strings are authored
    by us, but a stray `&` in a description silently produces a .vsix that VS
    Code refuses with an unhelpful parse error."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def collect(source: Path) -> list[Path]:
    """Every file to ship, sorted so the archive is byte-stable across runs."""
    out = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_NAMES for part in path.relative_to(source).parts):
            continue
        out.append(path)
    return out


def build(source: Path = SOURCE, out_dir: Path | None = None) -> Path:
    manifest_path = source / "package.json"
    if not manifest_path.is_file():
        raise SystemExit(f"No package.json in {source}")
    pkg = json.loads(manifest_path.read_text(encoding="utf-8"))

    out_dir = out_dir or HERE
    target = out_dir / f"{pkg['name']}-{pkg['version']}.vsix"

    files = collect(source)
    manifest = MANIFEST.format(
        name=escape(pkg["name"]),
        version=escape(pkg["version"]),
        publisher=escape(pkg.get("publisher", "local")),
        display_name=escape(pkg.get("displayName", pkg["name"])),
        description=escape(pkg.get("description", "")),
        engine=escape(pkg.get("engines", {}).get("vscode", "^1.85.0")),
    )

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("extension.vsixmanifest", manifest)
        for path in files:
            rel = path.relative_to(source).as_posix()
            zf.write(path, f"extension/{rel}")

    print(f"{target}  ({target.stat().st_size / 1024:.1f} KB, {len(files)} files)")
    print("\nInstall with:\n")
    print(f"    code --install-extension {target}")
    return target


if __name__ == "__main__":
    build(out_dir=Path(sys.argv[1]) if len(sys.argv) > 1 else None)
