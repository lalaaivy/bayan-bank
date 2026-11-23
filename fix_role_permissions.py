
from pathlib import Path
import ast
import shutil
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent

CHANGES = {
    "loans/views.py": {
        'STAFF = ("admin", "staff", "loan_officer")':
            'STAFF = ("admin", "staff", "loan_officer")',

        'DECIDERS = ("admin", "loan_officer")':
            'DECIDERS = ("loan_officer",)',

        'DISBURSERS = ("admin", "staff")':
            'DISBURSERS = ("staff",)',

        'PAYMENT_TAKERS = ("admin", "staff")':
            'PAYMENT_TAKERS = ("staff",)',

        '@role_required(*STAFF)\n@require_POST\ndef staff_create_agreement':
            '@role_required(*DECIDERS)\n@require_POST\ndef staff_create_agreement',
    },

    "loans/services.py": {
        'DECIDERS = ("admin", "loan_officer")':
            'DECIDERS = ("loan_officer",)',

        'DISBURSERS = ("admin", "staff")':
            'DISBURSERS = ("staff",)',

        'PAYMENT_TAKERS = ("admin", "staff")':
            'PAYMENT_TAKERS = ("staff",)',
    },

    "savings/views.py": {
        'STAFF_VIEWERS = ("admin", "staff", "loan_officer")':
            'STAFF_VIEWERS = ("admin", "staff", "loan_officer")',

        'CASHIERS = ("admin", "staff")':
            'CASHIERS = ("staff",)',
    },
}


def update_files():
    prepared = []

    # First validate every requested change.
    # Do not modify anything if a file differs
    # from the expected source.
    for relative_path, replacements in CHANGES.items():
        path = BASE_DIR / relative_path

        if not path.is_file():
            raise FileNotFoundError(
                f"Missing file: {relative_path}"
            )

        original = path.read_text(encoding="utf-8")
        updated = original

        for old, new in replacements.items():
            if old == new:
                # Existing read-only access remains unchanged.
                continue

            count = updated.count(old)

            if count != 1:
                raise RuntimeError(
                    f"{relative_path}: expected exactly one "
                    f"match for {old!r}, found {count}. "
                    "No files have been modified."
                )

            updated = updated.replace(old, new, 1)

        # Verify that updated Python remains valid.
        ast.parse(updated, filename=str(path))

        prepared.append(
            (path, original, updated)
        )

    # Back up existing source files before writing.
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = BASE_DIR / (
        f"role_permissions_backup_{timestamp}"
    )

    backup_dir.mkdir(exist_ok=False)

    for path, original, updated in prepared:
        relative_path = path.relative_to(BASE_DIR)

        backup_path = backup_dir / relative_path
        backup_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(path, backup_path)

    # Apply all validated changes.
    for path, original, updated in prepared:
        if original != updated:
            path.write_text(
                updated,
                encoding="utf-8",
            )

        print(
            f"Updated: {path.relative_to(BASE_DIR)}"
        )

    print()
    print("Role permission update completed.")
    print(f"Backups: {backup_dir.name}")
    print("No database changes were made.")


if __name__ == "__main__":
    update_files()
