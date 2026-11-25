"""Exception types used across the Pitch toolchain."""


class PitchError(Exception):
    """Base class for every error raised by the Pitch toolchain."""

    def __init__(self, message, line=None, where=None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.where = where

    def __str__(self):
        if self.line is None:
            return self.message
        prefix = "line {}".format(self.line)
        if self.where and self.where != "<main>":
            prefix += " in {}()".format(self.where)
        return "{}: {}".format(prefix, self.message)


class FlavourError(PitchError):
    """A flavour file is missing, malformed or contains an invalid alias."""


class PitchSyntaxError(PitchError):
    """The source code could not be tokenized, parsed or compiled."""


class PitchRuntimeError(PitchError):
    """The virtual machine failed while executing bytecode."""
