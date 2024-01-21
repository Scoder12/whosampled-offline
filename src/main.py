from dataclasses import dataclass
from typing import Any, List
import re

import requests
import lxml.html
from lxml.html import HtmlElement
from lxml.cssselect import CSSSelector


WS_DOMAIN = "https://www.whosampled.com"
UA = "WhoSampledOffline/v1.0 +https://github.com/Scoder12/whosampled-offline"


def fetch_document(sess: requests.Session, url: str) -> (str, HtmlElement):
    print("Fetching", url)
    r = sess.get(url, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.url, lxml.html.fromstring(r.text)


def assert_one(l: List[Any]) -> Any:
    assert len(l) == 1, f"Expected a single item, got {len(l)}"
    return l[0]


def take_text(l: List[HtmlElement]) -> str:
    elt = assert_one(l)
    return elt.text_content().strip()


def extract_url(current_url: str, e: HtmlElement) -> str:
    e.make_links_absolute(current_url)
    return e.get("href")


@dataclass
class PartialArtist:
    ws_artist_id: str
    name: str


@dataclass
class PartialTrack:
    name: str
    year: int
    more_link: str


def parse_artist(ws_artist_id: str, root: HtmlElement) -> PartialArtist:
    artist_name = take_text(root.cssselect(".artistName"))
    return PartialArtist(ws_artist_id=ws_artist_id, name=artist_name)


def parse_tracks(url: str, root: HtmlElement) -> List[PartialTrack]:
    tracks = []
    sel_more_link = CSSSelector(".trackName a[itemprop=url]")
    sel_name = CSSSelector(".trackName span[itemprop=name]")
    sel_year = CSSSelector(".trackName .trackYear")
    year_re = re.compile(r"\((\d+)\)")
    for track_tree in root.cssselect(".trackList .trackItem"):
        name = take_text(sel_name(track_tree))
        year_text = take_text(sel_year(track_tree))
        year = year_re.fullmatch(year_text).group(1)
        more_link = extract_url(url, assert_one(sel_more_link(track_tree)))
        tracks.append(PartialTrack(name=name, year=int(year), more_link=more_link))
    return tracks


def scrape_artist_page(sess: requests.Session, ws_artist_id: str) -> (PartialArtist, List[PartialTrack]):
    url, doc = fetch_document(sess, WS_DOMAIN + "/" + ws_artist_id)
    artist = parse_artist(ws_artist_id, doc)
    tracks = parse_tracks(url, doc)

    sel_next_page = CSSSelector(".pagination .next a")
    while True:
        next_elts = sel_next_page(doc)
        if len(next_elts) == 0:
            break
        next_url = extract_url(url, assert_one(next_elts))
        url, doc = fetch_document(sess, next_url)
        tracks += parse_tracks(url, doc)
    return artist, tracks


def main():
    sess = requests.Session()
    artist, tracks = scrape_artist_page(sess, "Leroy")
    print(artist)
    print(tracks)


if __name__ == "__main__":
    main()
