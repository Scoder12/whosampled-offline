import sys
import sqlite3

import requests

import scraper
from scraper import scrape_artist_page, scrape_track_page


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
            FOREIGN KEY(artist_id) REFERENCES artists(id)
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
            FOREIGN KEY(artist_id) REFERENCES artists(id)
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
            FOREIGN KEY(track_id) REFERENCES tracks(id)
        )
            """
        )
        db.execute(
            """
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY,
            track_id INTEGER,
            sampled_track_id INTEGER,
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
            (track.name, artist_id, track.year, track.more_link)
        ).fetchone()
        db.executemany(
            "INSERT INTO art (track_id, res_multiplier, url) VALUES (?, ?, ?)",
            [(track_id, float(res_multiplier), img_url) for res_multiplier, img_url in track.art.sources]
        )

        for sample in scrape_track_page(track.more_link.rstrip("/") + "/samples"):
            (sampled_artist_id,) = db.execute(
                "INSERT INTO artists (ws_id, name) VALUES (?, ?) RETURNING id",
                (sample.artist.ws_id, sample.artist.name)
            ).fetchone()
            (sampled_track_id,) = db.execute(
                "INSERT INTO tracks (name, artist_id, year, link) VALUES (?, ?, ?, ?) RETURNING id",
                (sample.song, sampled_artist_id, sample.year, track.more_link)
            ).fetchone()


    print(artist_id)


if __name__ == "__main__":
    main()
