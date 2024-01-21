import sys
import sqlite3

import requests

import scraper
from scraper import scrape_artist_page, scrape_samples


def setup_db(db):
    db.execute("PRAGMA foreign_keys = ON;")
    (schema_version,) = db.execute("PRAGMA user_version;").fetchone()

    if schema_version == 0:
        db.execute(
            """
        CREATE TABLE artists (
            id INTEGER PRIMARY KEY,
            ws_id TEXT UNIQUE,
            name TEXT
        )
            """
        )
        db.execute(
            """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY,
            name TEXT,
            artist_id INTEGER,
            year INTEGER,
            link TEXT UNIQUE,
            FOREIGN KEY(artist_id) REFERENCES artists(id),
            UNIQUE (name, artist_id, year)
        )
            """
        )
        db.execute(
            """
        CREATE TABLE features (
            id INTEGER PRIMARY KEY,
            track_id INTEGER,
            artist_id INTEGER,
            FOREIGN KEY(track_id) REFERENCES tracks(id),
            FOREIGN KEY(artist_id) REFERENCES artists(id),
            UNIQUE (track_id, artist_id)
        )
            """
        )
        db.execute(
            """
        CREATE TABLE art (
            id INTEGER PRIMARY KEY,
            track_id INTEGER,
            res_multiplier REAL,
            url TEXT,
            FOREIGN KEY(track_id) REFERENCES tracks(id),
            UNIQUE (track_id, res_multiplier)
        )
            """
        )
        db.execute(
            """
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY,
            track_id INTEGER,
            sampled_track_id INTEGER,
            FOREIGN KEY(track_id) REFERENCES tracks(id),
            FOREIGN KEY(sampled_track_id) REFERENCES tracks(id),
            UNIQUE (track_id, sampled_track_id)
        )
            """
        )

    db.execute("PRAGMA user_version = 1;")
    db.commit()


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <db.sqlite3>", file=sys.stderr)
        sys.exit(1)
    _, db_filename = sys.argv

    db = sqlite3.connect(db_filename)
    setup_db(db)
    sess = requests.Session()

    artist, tracks = scrape_artist_page(sess, "Leroy")
    (artist_id,) = db.execute(
        "INSERT INTO artists (ws_id, name) VALUES (?, ?) RETURNING id",
        (artist.ws_id, artist.name),
    ).fetchone()
    for track in tracks:
        (track_id,) = db.execute(
            "INSERT INTO tracks (name, artist_id, year, link) VALUES (?, ?, ?, ?) RETURNING id",
            (track.name, artist_id, track.year, track.more_link),
        ).fetchone()
        db.executemany(
            "INSERT INTO art (track_id, res_multiplier, url) VALUES (?, ?, ?)",
            [
                (track_id, float(res_multiplier), img_url)
                for res_multiplier, img_url in track.art.sources
            ],
        )

        samples = scrape_samples(sess, track.more_link)
        for sample in samples:
            (sampled_artist_id,) = (
                db.execute(
                    "INSERT OR IGNORE INTO artists (ws_id, name) VALUES (?, ?) RETURNING id",
                    (sample.artist.ws_id, sample.artist.name),
                ).fetchone()
                or db.execute(
                    "SELECT id FROM artists WHERE ws_id = ? AND name = ?",
                    (sample.artist.ws_id, sample.artist.name),
                ).fetchone()
            )
            r = db.execute(
                "INSERT OR IGNORE INTO tracks (name, artist_id, year, link) VALUES (?, ?, ?, ?) RETURNING id",
                (sample.song, sampled_artist_id, sample.year, sample.more_link),
            ).fetchone()
            if r is not None:
                # the sampled track does not yet exist. populate it.
                (sampled_track_id,) = r
                for feature in sample.features:
                    (feature_id,) = (
                        db.execute(
                            "INSERT OR IGNORE INTO artists (ws_id, name) VALUES (?, ?) RETURNING id",
                            (feature.ws_id, feature.name),
                        ).fetchone()
                        or db.execute(
                            "SELECT id FROM artists WHERE ws_id = ? AND name = ?",
                            (feature.ws_id, feature.name),
                        ).fetchone()
                    )
                    db.execute(
                        "INSERT INTO features(track_id, artist_id) VALUES (?, ?)",
                        (sampled_track_id, feature_id),
                    )
                db.executemany(
                    "INSERT INTO art (track_id, res_multiplier, url) VALUES (?, ?, ?)",
                    [
                        (sampled_track_id, float(res_multiplier), img_url)
                        for res_multiplier, img_url in sample.art.sources
                    ],
                )
            else:
                # use the existing sampled track from the DB
                (sampled_track_id,) = db.execute(
                    "SELECT id FROM tracks WHERE name = ? AND artist_id = ? AND year = ?",
                    (sample.song, sampled_artist_id, sample.year),
                ).fetchone()
            db.execute(
                "INSERT INTO samples(track_id, sampled_track_id) VALUES (?, ?)",
                (track_id, sampled_track_id),
            )
    db.commit()


if __name__ == "__main__":
    main()
