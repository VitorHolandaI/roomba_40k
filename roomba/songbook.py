"""Monophonic melodies the Roomba's own beeper plays via SCI createSong.

The iRobot Create/Roomba OI stores up to 16 note/duration pairs per song
(opcode 140, ``createSong``) and plays a slot with opcode 141 (``playSong``).
Notes are MIDI numbers (31-127 audible; below 31 = rest/silence); durations
are in 1/64 s ticks (1-255). This is the RPi-independent audio path: sound
comes out of the robot's internal piezo, not the USB speaker that
``media.music`` drives.

Example::

    notes = notes_for(0)          # flat (note, dur, note, dur, ...) tuple
    duration = bot.play_song(0, notes)
"""

from typing import NamedTuple, Tuple

# A note is (midi_number, duration_ticks). midi < MIN_AUDIBLE => rest.
Note = Tuple[int, int]

MAX_NOTES = 16          # OI hard limit: 16 note/duration pairs per song slot.
MIN_AUDIBLE = 31        # OI plays MIDI 31-127; below 31 is silence.
MAX_MIDI = 127
MAX_TICKS = 255         # duration byte is unsigned; 255 ticks ~ 3.98 s.
REST = 30               # any value < MIN_AUDIBLE silences; explicit for reading.

# Note-duration ticks (1/64 s): S=eighth, E=quarter-ish, Q=half, H=whole-ish.
S, E, Q, H = 8, 16, 32, 48


class Song(NamedTuple):
    """A named monophonic melody, at most ``MAX_NOTES`` note/duration pairs."""

    title: str
    notes: Tuple[Note, ...]


# Public, well-known monophonic riffs. Each stays <= 16 notes so it fits one
# OI song slot without chaining. MIDI: middle C = 60, A4 = 69.
SONGBOOK: Tuple[Song, ...] = (
    Song(
        "Imperial March",
        (
            (55, Q), (55, Q), (55, Q), (51, 24), (58, S),
            (55, Q), (51, 24), (58, S), (55, H),
        ),
    ),
    Song(
        "Mario",
        (
            (76, E), (76, E), (REST, E), (76, E), (REST, E),
            (72, E), (76, E), (REST, E), (79, E), (REST, E), (67, Q),
        ),
    ),
    Song(
        "Zelda Secret",
        (
            (79, S), (78, S), (75, S), (69, S),
            (68, S), (76, S), (80, S), (84, Q),
        ),
    ),
    Song(
        "Ode to Joy",
        (
            (64, Q), (64, Q), (65, Q), (67, Q), (67, Q), (65, Q), (64, Q),
            (62, Q), (60, Q), (60, Q), (62, Q), (64, Q), (64, 24), (62, S),
            (62, H),
        ),
    ),
    Song(
        "Tetris",
        (
            (76, Q), (71, E), (72, E), (74, Q), (72, E), (71, E), (69, Q),
            (69, E), (72, E), (76, Q), (74, E), (72, E), (71, Q),
        ),
    ),
)


def song_titles() -> list[str]:
    """Ordered titles for the UI selector; index matches ``notes_for``."""
    return [song.title for song in SONGBOOK]


def notes_for(index: int) -> Tuple[int, ...]:
    """Flat ``(note, dur, note, dur, ...)`` tuple ready for ``createSong``.

    Raises ``IndexError`` with the offending index when out of range.
    """
    if not 0 <= index < len(SONGBOOK):
        raise IndexError(
            f"song index {index} out of range; expected 0..{len(SONGBOOK) - 1}"
        )
    return _flatten(SONGBOOK[index].notes)


def _flatten(notes: Tuple[Note, ...]) -> Tuple[int, ...]:
    """Interleave (note, dur) pairs into the flat tuple the OI expects."""
    flat: list[int] = []
    for midi, ticks in notes:
        flat.extend((midi, ticks))
    return tuple(flat)
