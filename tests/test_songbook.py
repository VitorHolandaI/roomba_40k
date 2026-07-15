"""Songbook data integrity + accessor tests."""

import pytest

from roomba.songbook import (
    MAX_MIDI,
    MAX_NOTES,
    MAX_TICKS,
    SONGBOOK,
    notes_for,
    song_titles,
)


def test_every_song_fits_one_oi_slot() -> None:
    for song in SONGBOOK:
        assert 1 <= len(song.notes) <= MAX_NOTES, song.title


def test_notes_within_oi_byte_ranges() -> None:
    for song in SONGBOOK:
        for midi, ticks in song.notes:
            assert 0 <= midi <= MAX_MIDI, (song.title, midi)
            assert 1 <= ticks <= MAX_TICKS, (song.title, ticks)


def test_titles_are_unique() -> None:
    titles = song_titles()
    assert len(titles) == len(set(titles))


def test_song_titles_matches_songbook_order() -> None:
    assert song_titles() == [song.title for song in SONGBOOK]


def test_notes_for_flattens_pairs() -> None:
    flat = notes_for(0)
    assert len(flat) == 2 * len(SONGBOOK[0].notes)
    assert flat[0] == SONGBOOK[0].notes[0][0]
    assert flat[1] == SONGBOOK[0].notes[0][1]


def test_notes_for_rejects_out_of_range() -> None:
    with pytest.raises(IndexError, match="out of range"):
        notes_for(len(SONGBOOK))
    with pytest.raises(IndexError, match="out of range"):
        notes_for(-1)
