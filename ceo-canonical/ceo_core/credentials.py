from __future__ import annotations

from abc import ABC, abstractmethod
import ctypes
import ctypes.wintypes
import os
from dataclasses import dataclass
from typing import Dict


class SecretStore(ABC):
    @abstractmethod
    def put(self, key: str, value: str) -> None: ...
    @abstractmethod
    def get(self, key: str) -> str | None: ...
    @abstractmethod
    def delete(self, key: str) -> None: ...


class MemorySecretStore(SecretStore):
    """Test-only volatile store."""
    def __init__(self) -> None: self._data: Dict[str, str] = {}
    def put(self, key: str, value: str) -> None: self._data[key] = value
    def get(self, key: str) -> str | None: return self._data.get(key)
    def delete(self, key: str) -> None: self._data.pop(key, None)


@dataclass(slots=True)
class SecretReference:
    service: str
    key: str
    storage: str


class WindowsDPAPISecretStore(SecretStore):
    """Windows-only DPAPI user-scope secret store backed by protected environment payloads.

    The encrypted blob may be persisted by the caller; plaintext is never written here.
    This implementation intentionally refuses to operate on non-Windows systems.
    """
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("WindowsDPAPISecretStore is only available on Windows")
        self._data: Dict[str, bytes] = {}

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    def _blob(self, data: bytes):
        buf = ctypes.create_string_buffer(data)
        return self.DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf

    def _protect(self, data: bytes) -> bytes:
        in_blob, keep = self._blob(data); out_blob = self.DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            raise ctypes.WinError()
        try: return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally: ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    def _unprotect(self, data: bytes) -> bytes:
        in_blob, keep = self._blob(data); out_blob = self.DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            raise ctypes.WinError()
        try: return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally: ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    def put(self, key: str, value: str) -> None: self._data[key] = self._protect(value.encode())
    def get(self, key: str) -> str | None:
        blob = self._data.get(key); return self._unprotect(blob).decode() if blob else None
    def delete(self, key: str) -> None: self._data.pop(key, None)

class WindowsCredentialManagerStore(SecretStore):
    """Persistent Windows Credential Manager backend (Generic credentials)."""
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.wintypes.DWORD), ("Type", ctypes.wintypes.DWORD),
            ("TargetName", ctypes.wintypes.LPWSTR), ("Comment", ctypes.wintypes.LPWSTR),
            ("LastWritten", ctypes.wintypes.FILETIME), ("CredentialBlobSize", ctypes.wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", ctypes.wintypes.DWORD),
            ("AttributeCount", ctypes.wintypes.DWORD), ("Attributes", ctypes.c_void_p),
            ("TargetAlias", ctypes.wintypes.LPWSTR), ("UserName", ctypes.wintypes.LPWSTR),
        ]

    def __init__(self, namespace: str = "CEO-de-IAs") -> None:
        if os.name != "nt":
            raise RuntimeError("WindowsCredentialManagerStore is only available on Windows")
        self.namespace = namespace
        self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)

    def _target(self, key: str) -> str: return f"{self.namespace}:{key}"

    def put(self, key: str, value: str) -> None:
        raw = value.encode("utf-16-le")
        buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        cred = self.CREDENTIALW()
        cred.Type = self.CRED_TYPE_GENERIC
        cred.TargetName = self._target(key)
        cred.CredentialBlobSize = len(raw)
        cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = "CEO"
        if not self.advapi.CredWriteW(ctypes.byref(cred), 0): raise ctypes.WinError()

    def get(self, key: str) -> str | None:
        pcred = ctypes.POINTER(self.CREDENTIALW)()
        if not self.advapi.CredReadW(self._target(key), self.CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
            err = ctypes.get_last_error()
            if err == 1168: return None
            raise ctypes.WinError(err)
        try:
            cred = pcred.contents
            if not cred.CredentialBlob or not cred.CredentialBlobSize: return ""
            raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            self.advapi.CredFree(pcred)

    def delete(self, key: str) -> None:
        if not self.advapi.CredDeleteW(self._target(key), self.CRED_TYPE_GENERIC, 0):
            err = ctypes.get_last_error()
            if err != 1168: raise ctypes.WinError(err)


class MirroredSecretStore(SecretStore):
    """Write secrets to two stores and self-heal the primary from the backup."""
    def __init__(self, primary: SecretStore, backup: SecretStore) -> None:
        self.primary = primary
        self.backup = backup

    def put(self, key: str, value: str) -> None:
        self.primary.put(key, value)
        self.backup.put(key, value)

    def get(self, key: str) -> str | None:
        value = self.primary.get(key)
        if value is not None:
            return value
        value = self.backup.get(key)
        if value is not None:
            try:
                self.primary.put(key, value)
            except Exception:
                pass
        return value

    def delete(self, key: str) -> None:
        first_error = None
        try:
            self.primary.delete(key)
        except Exception as exc:
            first_error = exc
        try:
            self.backup.delete(key)
        except Exception:
            if first_error is None:
                raise
        if first_error is not None:
            raise first_error


class WindowsDPAPIFileSecretStore(SecretStore):
    """Persistent DPAPI-encrypted file backup for small release secrets.

    Ciphertext is bound to the current Windows user. Plaintext is never written to
    disk. This is a recovery mirror, not a portable backup across Windows accounts.
    """
    CRYPTPROTECT_UI_FORBIDDEN = 0x1

    def __init__(self, root) -> None:
        from pathlib import Path
        if os.name != "nt":
            raise RuntimeError("WindowsDPAPIFileSecretStore is only available on Windows")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str):
        import hashlib
        return self.root / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".dpapi")

    def _protect(self, data: bytes) -> bytes:
        helper = WindowsDPAPISecretStore()
        in_blob, keep = helper._blob(data); out_blob = helper.DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, self.CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob)):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    def _unprotect(self, data: bytes) -> bytes:
        helper = WindowsDPAPISecretStore()
        in_blob, keep = helper._blob(data); out_blob = helper.DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, self.CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob)):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    def put(self, key: str, value: str) -> None:
        path = self._path(key)
        tmp = path.with_name(path.name + ".tmp")
        blob = self._protect(value.encode("utf-8"))
        with tmp.open("wb") as f:
            f.write(blob); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)

    def get(self, key: str) -> str | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return self._unprotect(path.read_bytes()).decode("utf-8")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
