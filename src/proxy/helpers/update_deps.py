# /// script
# dependencies = [
#   "tomlkit==0.12.5"
# ]
# ///

import sys
from pathlib import Path
import tomllib
import tomlkit


def get_dep_name(dep: str) -> str:
    dep = dep.strip()
    # 1. Strip out package extras, e.g., "uvicorn[standard]" -> "uvicorn"
    if "[" in dep and "]" in dep:
        dep = dep.split("[")[0]

    # 2. Strip out version specifiers if they exist
    for sep in ["==", ">=", "<=", "~=", "!=", ">", "<"]:
        if sep in dep:
            dep = dep.split(sep)[0]

    return dep.strip()


def get_base_name(dep: str) -> str:
    """Extracts just the base package name for looking up in uv.lock.

    e.g., 'elasticsearch[async]>=8.0' -> 'elasticsearch'
    """
    dep = dep.strip()
    # Strip version specifiers first
    for sep in ["==", ">=", "<=", "~=", "!=", ">", "<"]:
        if sep in dep:
            dep = dep.split(sep)[0]
    # Strip extras block to get the pure package name
    if "[" in dep:
        dep = dep.split("[")[0]
    return dep.strip()


def get_prefix_with_extras(dep: str) -> str:
    """Extracts the package name and its extras block, ignoring versions.

    e.g., 'elasticsearch[async]>=8.0' -> 'elasticsearch[async]'
    """
    dep = dep.strip()
    for sep in ["==", ">=", "<=", "~=", "!=", ">", "<"]:
        if sep in dep:
            dep = dep.split(sep)[0]
    return dep.strip()


def pin_dependencies_inplace(dep_list, locked_versions: dict, section_name: str):
    """Mutates the existing tomlkit array in-place to preserve internal comments and extras."""
    if dep_list is None:
        return

    print(f"\n📦 {section_name}")
    print("─" * (len(section_name) + 3))

    for i in range(len(dep_list)):
        dep = str(dep_list[i])
        base_name = get_base_name(
            dep
        )  # Used for looking up in uv.lock ('elasticsearch')
        prefix_name = get_prefix_with_extras(
            dep
        )  # Used for rewriting the line ('elasticsearch[async]')

        if base_name in locked_versions:
            version = locked_versions[base_name]
            pinned = f"{prefix_name}=={version}"  # Recombines extras with the new version string
            dep_list[i] = pinned
            print(f"  ✅ Pinned:  {prefix_name.ljust(25)} -> {version}")
        else:
            print(f"  ⚠️  Skipped: {prefix_name.ljust(25)} (not in lock)")


def run_pinning(root_path: Path):
    pyproject_path = root_path / "pyproject.toml"
    lock_path = root_path / "uv.lock"

    if not lock_path.exists() or not pyproject_path.exists():
        print("❌ Error: Could not find pyproject.toml or uv.lock in this directory.")
        return

    # 1. Read Lock Data using fast built-in tomllib
    with open(lock_path, "rb") as f:
        lock_data = tomllib.load(f)

    locked_versions = {
        pkg["name"]: pkg["version"] for pkg in lock_data.get("package", [])
    }

    # 2. Load pyproject.toml using tomlkit
    with open(pyproject_path, "r", encoding="utf-8") as f:
        data = tomlkit.load(f)

    project = data.get("project", {})

    # Update Main Dependencies in-place
    if "dependencies" in project:
        pin_dependencies_inplace(
            project["dependencies"], locked_versions, "project.dependencies"
        )

    # Update Optional Dependencies in-place
    if "optional-dependencies" in project:
        optional = project["optional-dependencies"]
        for group in optional.keys():
            pin_dependencies_inplace(
                optional[group], locked_versions, f"optional-dependencies.{group}"
            )

    # Update Build Requirements in-place
    build_system = data.get("build-system", {})
    if "requires" in build_system:
        pin_dependencies_inplace(
            build_system["requires"], locked_versions, "build-system.requires"
        )

    # 3. Write data back out (The original comments and layout are perfectly preserved)
    with open(pyproject_path, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(data))

    print(f"\n✨ Successfully updated: {pyproject_path.name}\n")


def main():
    """Main entry point."""
    try:
        run_pinning(Path.cwd())
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Critical Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
