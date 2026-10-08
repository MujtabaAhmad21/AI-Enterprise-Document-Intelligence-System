"""Password hashing. SEC-002, SEC-018."""

import contextlib

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

# SEC-002: Argon2id, time_cost=3, memory_cost=64 MiB (argon2-cffi takes memory_cost in KiB).
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)

# A hash of a fixed, never-issued password, computed once at import time. Verifying against it
# on the unknown-user path costs the same CPU time as a real verification (SEC-018), so overall
# request latency does not reveal whether an email is registered.
_DUMMY_HASH = _hasher.hash("not-a-real-password-used-only-for-timing-equalisation")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def verify_dummy_password() -> None:
    """SEC-018: called on the unknown-user path so total latency is indistinguishable from a
    real verification attempt."""
    with contextlib.suppress(VerifyMismatchError):
        _hasher.verify(_DUMMY_HASH, "irrelevant")
