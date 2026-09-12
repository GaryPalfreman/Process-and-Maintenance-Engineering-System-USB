from usb_storage import removable_roots, initialise_vault


def main():
    roots = removable_roots()
    if not roots:
        print("No external drives detected. Connect the USB HDD/SSD and run this again.")
        return

    print("Detected external drives:")
    for index, root in enumerate(roots, start=1):
        print(f"  {index}. {root}")

    raw = input("Select drive number: ").strip()
    try:
        selected = roots[int(raw) - 1]
    except Exception:
        print("Invalid selection.")
        return

    label = input("Vault name [Engineering Vault]: ").strip() or "Engineering Vault"
    confirm = input(f"Create ENGINEERING_SYSTEM on {selected}? Type YES to continue: ").strip()
    if confirm != "YES":
        print("Cancelled.")
        return

    vault = initialise_vault(selected, label)
    print(f"Engineering Vault created at: {vault}")


if __name__ == "__main__":
    main()
