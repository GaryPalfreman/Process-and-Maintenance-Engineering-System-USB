"""Shared local USB/HDD runtime for the Streamlit edition.

The Engineering Vault is the durable store. The runtime wraps the loaded JSON
structure in observable dict/list containers so mutations anywhere in the app
are written back to the external drive automatically.
"""
from pathlib import Path
import streamlit as st

from usb_storage import find_vaults, load_from_vault, save_to_vault, create_backup, backup_due, vault_status


def _plain(value):
    """Return ordinary dict/list data without triggering observable callbacks."""
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in dict.items(value)}
    if isinstance(value, list):
        return [_plain(item) for item in list.__iter__(value)]
    return value


class _VaultController:
    def __init__(self, vault):
        self.vault = Path(vault)
        self.root = None
        self.suspended = False

    def changed(self):
        if self.suspended or self.root is None:
            return
        self.suspended = True
        try:
            payload = _plain(self.root)
            save_to_vault(self.vault, payload)
            if backup_due(self.vault):
                create_backup(self.vault, payload, "auto")
            st.session_state.usb_dirty = False
        finally:
            self.suspended = False


class VaultDict(dict):
    def __init__(self, source=None, controller=None):
        self._controller = controller
        dict.__init__(self)
        for key, value in (source or {}).items():
            dict.__setitem__(self, key, _wrap(value, controller))

    def _changed(self):
        if self._controller:
            self._controller.changed()

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, _wrap(value, self._controller))
        self._changed()

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self._changed()

    def clear(self):
        dict.clear(self)
        self._changed()

    def pop(self, key, *args):
        value = dict.pop(self, key, *args)
        self._changed()
        return value

    def popitem(self):
        value = dict.popitem(self)
        self._changed()
        return value

    def setdefault(self, key, default=None):
        if key in self:
            return dict.__getitem__(self, key)
        value = _wrap(default, self._controller)
        dict.__setitem__(self, key, value)
        self._changed()
        return value

    def update(self, *args, **kwargs):
        incoming = dict(*args, **kwargs)
        for key, value in incoming.items():
            dict.__setitem__(self, key, _wrap(value, self._controller))
        self._changed()


class VaultList(list):
    def __init__(self, source=None, controller=None):
        self._controller = controller
        list.__init__(self, [_wrap(value, controller) for value in (source or [])])

    def _changed(self):
        if self._controller:
            self._controller.changed()

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            value = [_wrap(v, self._controller) for v in value]
        else:
            value = _wrap(value, self._controller)
        list.__setitem__(self, key, value)
        self._changed()

    def __delitem__(self, key):
        list.__delitem__(self, key)
        self._changed()

    def append(self, value):
        list.append(self, _wrap(value, self._controller))
        self._changed()

    def extend(self, values):
        list.extend(self, [_wrap(v, self._controller) for v in values])
        self._changed()

    def insert(self, index, value):
        list.insert(self, index, _wrap(value, self._controller))
        self._changed()

    def pop(self, index=-1):
        value = list.pop(self, index)
        self._changed()
        return value

    def remove(self, value):
        list.remove(self, value)
        self._changed()

    def clear(self):
        list.clear(self)
        self._changed()

    def reverse(self):
        list.reverse(self)
        self._changed()

    def sort(self, *args, **kwargs):
        list.sort(self, *args, **kwargs)
        self._changed()

    def __iadd__(self, values):
        self.extend(values)
        return self


def _wrap(value, controller):
    if isinstance(value, (VaultDict, VaultList)):
        return value
    if isinstance(value, dict):
        return VaultDict(value, controller)
    if isinstance(value, list):
        return VaultList(value, controller)
    return value


def _observable_store(raw_store, vault):
    controller = _VaultController(vault)
    wrapped = _wrap(raw_store, controller)
    controller.root = wrapped
    st.session_state.usb_controller = controller
    return wrapped


def require_vault():
    """Locate one Engineering Vault and load its live store."""
    vaults = find_vaults()
    if not vaults:
        st.error("Engineering Vault not connected. Connect the M-P-ENG-SYS drive and refresh this page.")
        st.stop()
    if len(vaults) > 1:
        st.error("More than one Engineering Vault is connected. Disconnect the extra vault and refresh.")
        st.stop()

    vault = Path(vaults[0])
    vault_key = str(vault.resolve())
    current = st.session_state.get("pm_store")
    if st.session_state.get("usb_vault_path") != vault_key or current is None:
        try:
            current = _observable_store(load_from_vault(vault), vault)
            st.session_state.pm_store = current
            st.session_state.usb_vault_path = vault_key
            st.session_state.usb_dirty = False
        except Exception as exc:
            st.error(f"Engineering Vault could not be loaded: {exc}")
            st.stop()
    elif not isinstance(current, VaultDict):
        current = _observable_store(current, vault)
        st.session_state.pm_store = current
    return vault, current


def persist(store=None, backup=True):
    """Force an immediate atomic save of the current engineering store."""
    vaults = find_vaults()
    if len(vaults) != 1:
        st.error("Engineering Vault is no longer available. Reconnect it before continuing.")
        st.stop()
    vault = Path(vaults[0])
    data = _plain(store if store is not None else st.session_state.pm_store)
    save_to_vault(vault, data)
    if backup and backup_due(vault):
        create_backup(vault, data, "auto")
    st.session_state.usb_dirty = False
    return vault


def vault_sidebar(vault):
    """Compact vault status and manual safety controls shown on every page."""
    info = vault_status(vault)
    free_gb = info.get("free_bytes", 0) / (1024 ** 3)
    st.sidebar.success("Engineering Vault Connected")
    st.sidebar.caption(info.get("label", "Engineering Vault"))
    st.sidebar.caption(info.get("path", str(vault)))
    st.sidebar.caption(f"Free space: {free_gb:.1f} GB")
    st.sidebar.caption("Autosave: ON")
    if st.sidebar.button("Save to Engineering Vault", use_container_width=True):
        persist()
        st.sidebar.success("Saved")
    if st.sidebar.button("Create Vault Backup", use_container_width=True):
        target = create_backup(vault, _plain(st.session_state.pm_store), "manual")
        st.sidebar.success(f"Backup created: {target.name}")


def initialise_page():
    vault, store = require_vault()
    vault_sidebar(vault)
    return vault, store
