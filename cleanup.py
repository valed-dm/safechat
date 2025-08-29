from pathlib import Path
import shutil


def clean_pycache():
    """
    Finds and recursively deletes all __pycache__ directories
    starting from the project's root directory.
    """
    project_root = Path(__file__).parent
    print("--- Running cleanup script ---")

    deleted_count = 0
    # The .glob('**/__pycache__') pattern is powerful:
    # ** means "search recursively in all subdirectories"
    for path in project_root.glob("**/__pycache__"):
        if path.is_dir():
            try:
                shutil.rmtree(path)
                print(f"Deleted: {path}")
                deleted_count += 1
            except OSError as e:
                print(f"Error deleting {path}: {e}")

    if deleted_count > 0:
        print(f"Successfully deleted {deleted_count} __pycache__ director(y/ies).")
    else:
        print("No __pycache__ directories found to delete.")
    print("--- Cleanup finished ---")


if __name__ == "__main__":
    clean_pycache()
