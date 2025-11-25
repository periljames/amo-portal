import random
import string


def _random_block(length: int = 8) -> str:
    """
    Return a random string of uppercase letters and digits.
    """
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=length))


def generate_user_id(prefix: str = "ID") -> str:
    """
    Generate a short ID like 'AMO-1F2A9C3D' or 'ID-8K2L0P9Q'.

    IMPORTANT:
    - This function is used by SQLAlchemy as a column default.
    - SQLAlchemy will call it with **zero** positional arguments,
      so the function must work when called as `generate_user_id()`.
    - It must also not have more than ONE positional parameter.

    `prefix`:
      Optional prefix for the ID. When used as a column default
      with no arguments, it will use the default prefix "ID".
    """
    block = _random_block(8)
    if prefix:
        return f"{prefix}-{block}"
    return block
