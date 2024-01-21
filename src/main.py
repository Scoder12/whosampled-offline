import requests

import scraper
from scraper import scrape_artist_page, scrape_track_page


def main():
    sess = requests.Session()
    # artist, tracks = scrape_artist_page(sess, "Leroy", limit=1)
    # print(artist)
    # print(tracks)
    track = scraper.PartialTrack(
        name="The Joke Is on You",
        year=2022,
        more_link="https://www.whosampled.com/Leroy/Her-Head-Is-So0o0o0o0-Rolling-(POST-MORTEM-MIX)/",
    )
    samples = scrape_track_page(sess, track.more_link.rstrip("/") + "/samples")
    print(samples)


if __name__ == "__main__":
    main()
