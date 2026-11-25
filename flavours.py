"""Flavour (dialect) definitions: keyword and built-in function renaming.

A flavour is a JSON file that maps canonical Python words to new words:

    {
      "description": "Short text shown by 'pitch flavour list'",
      "keywords": {"if": "appeal", "while": "innings"},
      "builtins": {"print": "scoreboard", "len": "balls"}
    }

Keys are the canonical Python names, values are the flavour words. Any item that
is not listed keeps its normal Python name, and the normal English words always
keep working in every flavour.
"""
import json
import keyword
import os
import re
from pathlib import Path

from .errors import FlavourError

CANONICAL_KEYWORDS = (
    "if", "elif", "else", "while", "for", "in", "True", "False", "None",
    "and", "or", "not", "def", "return", "break", "continue", "pass",
    "class", "try", "except", "finally", "raise", "import", "from", "with",
    "as", "lambda",
)

CANONICAL_BUILTINS = (
    "print", "input", "len", "str", "int", "float", "bool", "abs", "round",
    "min", "max", "sum", "range", "sorted", "list",
)

DEFAULT_FLAVOUR = "cricket"
ENV_VAR = "PITCH_FLAVOURS"
BUILTIN_DIR = Path(__file__).resolve().parent / "flavours"

_ALLOWED_TOP_LEVEL = {"description", "keywords", "builtins"}
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_DIRECTIVE_RE = re.compile(r"^\s*#\s*flavou?r\s*:\s*([A-Za-z][A-Za-z0-9_]*)\s*$", re.IGNORECASE)


def check_alias(alias, canonical, flavour_name="?"):
    """Raise FlavourError when ``alias`` cannot be used for ``canonical``."""
    prefix = "flavour '{}': ".format(flavour_name)
    if not isinstance(alias, str) or not alias.isidentifier():
        raise FlavourError("{}{!r} is not a valid single-word identifier (for '{}')".format(
            prefix, alias, canonical))
    if alias == canonical:
        return
    if keyword.iskeyword(alias):
        raise FlavourError("{}{!r} is already a Python keyword and cannot be used for '{}'".format(
            prefix, alias, canonical))
    if alias in CANONICAL_BUILTINS:
        raise FlavourError("{}{!r} is already a built-in function name and cannot be used for '{}'".format(
            prefix, alias, canonical))


class Flavour:
    """A validated flavour. ``keywords`` and ``builtins`` map canonical -> alias."""

    def __init__(self, name, description="", keywords=None, builtins=None, path=None):
        self.name = name
        self.description = description
        self.path = path
        self.keywords = dict(keywords or {})
        self.builtins = dict(builtins or {})
        self.keyword_aliases = self._invert("keyword", self.keywords, CANONICAL_KEYWORDS)
        self.builtin_aliases = self._invert("built-in", self.builtins, CANONICAL_BUILTINS)
        clash = set(self.keyword_aliases) & set(self.builtin_aliases)
        if clash:
            raise FlavourError("flavour '{}': word {!r} is used for both a keyword and a built-in".format(
                name, sorted(clash)[0]))

    def _invert(self, kind, table, allowed):
        aliases = {}
        for canonical, alias in table.items():
            if canonical not in allowed:
                raise FlavourError("flavour '{}': unknown {} {!r}. Allowed: {}".format(
                    self.name, kind, canonical, ", ".join(allowed)))
            check_alias(alias, canonical, self.name)
            if alias == canonical:
                continue
            if alias in aliases:
                raise FlavourError("flavour '{}': word {!r} is used for both '{}' and '{}'".format(
                    self.name, alias, aliases[alias], canonical))
            aliases[alias] = canonical
        return aliases

    def alias_for(self, canonical):
        """Return the word this flavour uses for a canonical keyword or built-in."""
        if canonical in self.keywords:
            return self.keywords[canonical]
        if canonical in self.builtins:
            return self.builtins[canonical]
        return canonical

    def to_dict(self):
        """Full description with every canonical item listed (alias or itself)."""
        return {
            "description": self.description,
            "keywords": {name: self.alias_for(name) for name in CANONICAL_KEYWORDS},
            "builtins": {name: self.alias_for(name) for name in CANONICAL_BUILTINS},
        }


def _identity_flavour():
    return Flavour("python", "Plain Python words (no renaming).")


def load_flavour_file(path):
    path = Path(path)
    try:
        with open(str(path), encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise FlavourError("flavour file {} is not valid JSON: {}".format(path, exc))
    except OSError as exc:
        raise FlavourError("cannot read flavour file {}: {}".format(path, exc))
    if not isinstance(data, dict):
        raise FlavourError("flavour file {} must contain a JSON object".format(path))
    name = path.stem.lower()
    unknown = set(data) - _ALLOWED_TOP_LEVEL
    if unknown:
        raise FlavourError("flavour '{}': unknown field {!r}. Allowed fields: {}".format(
            name, sorted(unknown)[0], ", ".join(sorted(_ALLOWED_TOP_LEVEL))))
    for field_name in ("keywords", "builtins"):
        if not isinstance(data.get(field_name, {}), dict):
            raise FlavourError("flavour '{}': '{}' must be a JSON object".format(name, field_name))
    return Flavour(name, str(data.get("description", "")), data.get("keywords"),
                   data.get("builtins"), path)


def flavour_search_dirs():
    """Built-in flavours first, then ./flavours, then $PITCH_FLAVOURS (later wins)."""
    dirs = [BUILTIN_DIR, Path.cwd() / "flavours"]
    for part in os.environ.get(ENV_VAR, "").split(os.pathsep):
        if part.strip():
            dirs.append(Path(part.strip()))
    return dirs


def available_flavour_files():
    found = {}
    for directory in flavour_search_dirs():
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                found[path.stem.lower()] = path
    return found


def get_flavour(name=None):
    """Return a Flavour by name (or pass a Flavour through unchanged)."""
    if isinstance(name, Flavour):
        return name
    name = (name or DEFAULT_FLAVOUR).strip().lower()
    if name == "python":
        return _identity_flavour()
    files = available_flavour_files()
    if name not in files:
        choices = ", ".join(["python"] + sorted(files))
        raise FlavourError(
            "unknown flavour {!r}. Available: {}. Custom flavours are read from ./flavours "
            "or from the folders in ${}".format(name, choices, ENV_VAR))
    return load_flavour_file(files[name])


def list_flavours(errors=None):
    """All usable flavours. Broken files are skipped and described in ``errors``."""
    result = [_identity_flavour()]
    for name, path in sorted(available_flavour_files().items()):
        try:
            result.append(load_flavour_file(path))
        except FlavourError as exc:
            if errors is not None:
                errors.append(str(exc))
    return result


def detect_flavour(source):
    """Read a '# flavour: NAME' directive from the first lines of a source file."""
    for line in source.splitlines()[:5]:
        match = _DIRECTIVE_RE.match(line)
        if match:
            return match.group(1).lower()
    return None


def resolve_flavour(flavour=None, source=None):
    """Pick the flavour: explicit value, then source directive, then the default."""
    if flavour is None and source is not None:
        flavour = detect_flavour(source)
    return get_flavour(flavour)


def write_flavour_file(name, directory=None, base=None, description=None,
                       keywords=None, builtins=None, overwrite=False):
    """Create ``<directory>/<name>.json`` after validating it. Returns the path."""
    if not _NAME_RE.match(name or ""):
        raise FlavourError("flavour name {!r} must start with a letter and use only "
                           "letters, digits and underscores".format(name))
    name = name.lower()
    if name == "python":
        raise FlavourError("'python' is reserved for the plain Python flavour")
    base_flavour = get_flavour(base or "python")
    data = base_flavour.to_dict()
    data["description"] = description or "Custom flavour '{}'".format(name)
    data["keywords"].update(keywords or {})
    data["builtins"].update(builtins or {})
    Flavour(name, data["description"], data["keywords"], data["builtins"])  # validate
    target_dir = Path(directory) if directory else Path.cwd() / "flavours"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (name + ".json")
    if target.exists() and not overwrite:
        raise FlavourError("{} already exists".format(target))
    with open(str(target), "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target
