
from pathlib import Path
from datetime import datetime
import ast
import shutil

BASE = Path(__file__).resolve().parent

TARGETS = {
    "clients/urls.py": [
        "staff_clients",
        "staff_client_detail",
    ],
    "loans/urls.py": [
        "loan_applications",
        "loan_application_detail",
    ],
}


def main():
    changes = []

    for filename, names in TARGETS.items():
        path = BASE / filename

        if not path.is_file():
            raise RuntimeError(f"Missing: {filename}")

        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        url_list = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "urlpatterns"
                    for target in node.targets
                )
            ),
            None,
        )

        if url_list is None or not isinstance(
            url_list.value, ast.List
        ):
            raise RuntimeError(
                f"Unexpected urlpatterns format: {filename}"
            )

        lines = source.splitlines(keepends=True)
        ranges = []
        found = []

        for entry in url_list.value.elts:
            if not isinstance(entry, ast.Call):
                continue

            route_name = None

            for keyword in entry.keywords:
                if (
                    keyword.arg == "name"
                    and isinstance(keyword.value, ast.Constant)
                ):
                    route_name = keyword.value.value

            if route_name in names:
                found.append(route_name)
                ranges.append(
                    (entry.lineno, entry.end_lineno)
                )

        if sorted(found) != sorted(names):
            raise RuntimeError(
                f"{filename}: expected {names}, found {found}. "
                "No files changed."
            )

        # Remove only complete URL entries.
        # Keep imports and all unrelated routes.
        for start, end in sorted(
            ranges, reverse=True
        ):
            del lines[start - 1:end]

        updated = "".join(lines)

        # Verify the resulting Python is valid.
        ast.parse(updated, filename=filename)

        changes.append((path, source, updated))

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = BASE / f"url_backup_{timestamp}"
    backup.mkdir()

    for path, source, updated in changes:
        relative = path.relative_to(BASE)
        destination = backup / relative

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(path, destination)

    for path, source, updated in changes:
        path.write_text(
            updated,
            encoding="utf-8",
        )

        print(f"Updated: {path.relative_to(BASE)}")

    print()
    print("Duplicate URL entries removed.")
    print(f"Backup: {backup.name}")
    print("Database unchanged.")


if __name__ == "__main__":
    main()
