from dataclasses import dataclass
from typing import Any, List, Tuple
import re
from urllib.parse import urljoin

import requests
import lxml.html
from lxml.html import HtmlElement
from lxml.cssselect import CSSSelector


WS_DOMAIN = "https://www.whosampled.com"
UA = "WhoSampledOffline/v1.0 +https://github.com/Scoder12/whosampled-offline"


def make_request(sess: requests.Session, url: str) -> requests.Response:
    return sess.get(url, headers={"User-Agent": UA})


def fetch_document(sess: requests.Session, url: str) -> Tuple[str, HtmlElement]:
    print("Fetching", url)
    r = make_request(sess, url)
    r.raise_for_status()
    return r.url, lxml.html.fromstring(r.text)


def assert_one(l: List[Any]) -> Any:
    if not isinstance(l, list):
        raise AssertionError(f"assert_one called on {type(l)}, expected list")
    assert len(l) == 1, f"Expected a single item, got {len(l)}"
    return l[0]


def take_text(l: List[HtmlElement]) -> str:
    elt = assert_one(l)
    return elt.text_content().strip()


def extract_url(current_url: str, e: HtmlElement) -> str:
    e.make_links_absolute(current_url)
    return e.get("href")


@dataclass
class ArtRef:
    sources: List[Tuple[str, str]]


@dataclass
class PartialArtist:
    ws_id: str
    name: str


@dataclass
class PartialTrack:
    art: ArtRef
    name: str
    year: int
    more_link: str


def parse_art(url: str, cell: HtmlElement) -> ArtRef:
    img_elt = assert_one(cell.xpath("descendant-or-self::img"))
    images = {"1.0": urljoin(url, img_elt.get("src"))}
    pair_re = re.compile(r"(\S+) (\d+)x")
    for pair in img_elt.get("srcset").split(", "):
        pair_m = pair_re.fullmatch(pair)
        assert pair_m is not None, f"Expected {pair!r} to match regex"
        img_rel_url, res_num = pair_m.group(1), pair_m.group(2)
        img_url = urljoin(url, img_rel_url)
        res_num = round(float(res_num), ndigits=1)
        images[f"{res_num:.1f}"] = img_url
    return ArtRef(sources=list(images.items()))


def parse_artist(ws_id: str, root: HtmlElement) -> PartialArtist:
    artist_name = take_text(root.cssselect(".artistName"))
    return PartialArtist(ws_id=ws_id, name=artist_name)


def parse_tracks(url: str, root: HtmlElement) -> List[PartialTrack]:
    tracks = []
    sel_art = CSSSelector(".trackCover")
    sel_name = CSSSelector(".trackName span[itemprop=name]")
    sel_year = CSSSelector(".trackName .trackYear")
    sel_more_link = CSSSelector(".trackName a[itemprop=url]")
    year_re = re.compile(r"\((\d+)\)")
    for track_tree in root.cssselect(".trackList .trackItem"):
        art_ref = parse_art(url, assert_one(sel_art(track_tree)))
        name = take_text(sel_name(track_tree))
        year_text = take_text(sel_year(track_tree))
        year = year_re.fullmatch(year_text).group(1)
        more_link = extract_url(url, assert_one(sel_more_link(track_tree)))
        tracks.append(
            PartialTrack(art=art_ref, name=name, year=int(year), more_link=more_link)
        )
    return tracks


def scrape_artist_page(
    sess: requests.Session, ws_id: str
) -> Tuple[PartialArtist, List[PartialTrack]]:
    url, doc = fetch_document(sess, WS_DOMAIN + "/" + ws_id)
    artist = parse_artist(ws_id, doc)
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


@dataclass
class ArtistRef:
    name: str
    ws_id: str


@dataclass
class SampledTrack:
    art: ArtRef
    song: str
    artist: ArtistRef
    features: List[ArtistRef]
    year: int
    more_link: str


def parse_track_artists(cell: HtmlElement) -> Tuple[ArtistRef, List[ArtistRef]]:
    links = cell.xpath("descendant-or-self::a")
    assert len(links) >= 1, "Expected at least one artist link but got 0"
    ws_id_re = re.compile(r"\/(?:tv\/)?([A-Za-z0-9\-()\.]+)\/")
    artists = []
    for l in links:
        ws_id_m = ws_id_re.fullmatch(l.get("href"))
        assert ws_id_m is not None, f"Expected re to match: {l.get('href')!r}"
        artists.append(ArtistRef(name=take_text([l]), ws_id=ws_id_m.group(1)))
    return artists[0], artists[1:]


def scrape_dedi_samples_page(sess: requests.Session, url: str, doc: HtmlElement) -> List[SampledTrack]:
    url, doc = fetch_document(sess, url)
    samples = []
    sel_td = CSSSelector("td")
    for row in doc.cssselect("table.tdata > tbody > tr"):
        cells = sel_td(row)
        assert len(cells) == 5, f"Expected 5 cells in row, got {len(cells)}"
        art_cell, song_cell, artists_cell, year_cell, _sample_cell = cells
        artist, features = parse_track_artists(artists_cell)
        track = SampledTrack(
            art=parse_art(url, art_cell),
            song=take_text([song_cell]),
            artist=artist,
            features=features,
            year=int(take_text([year_cell])),
            more_link=extract_url(
                url, assert_one(song_cell.xpath("descendant-or-self::a"))
            ),
        )
        samples.append(track)
    return samples


def find_samples_table(doc: HtmlElement) -> List[HtmlElement]:
    sel_title = CSSSelector(".section-header-title")
    for section in doc.cssselect("section:has(.list)"):
        title = take_text(sel_title(section))
        if title.startswith("Contains samples of"):
            return section.cssselect(".list .listEntry")
    raise AssertionError("Unable to find sample tample")


def scrape_track_page_samples(
    sess: requests.Session, more_link: str
) -> List[SampledTrack]:
    url, doc = fetch_document(sess, more_link)
    samples = []
    sel_track_name = CSSSelector(".trackName")
    sel_track_artist = CSSSelector(".trackArtist")
    year_re = re.compile(r"\((\d+)\)\s*$")
    for sample_elt in find_samples_table(doc):
        artist_elt = assert_one(sel_track_artist(sample_elt))
        print(lxml.html.tostring(artist_elt))
        artist, features = parse_track_artists(artist_elt)
        track_name = assert_one(sel_track_name(sample_elt))
        year_text = take_text([artist_elt])
        year_m = year_re.search(year_text)
        assert year_m is not None, f"Expected {year_text!r} to match re"
        track = SampledTrack(
            art=parse_art(url, sample_elt),
            song=take_text([track_name]),
            artist=artist,
            features=features,
            year=int(year_m.group(1)),
            more_link=extract_url(url, track_name),
        )
        samples.append(track)
    return samples


def scrape_samples(sess: requests.Session, more_link: str) -> List[SampledTrack]:
    r = make_request(sess, more_link.rstrip("/") + "/samples")
    if r.status_code == 404:
        return scrape_track_page_samples(sess, more_link)
    r.raise_for_status()
    return scrape_dedi_samples_page(sess, r.url, lxml.html.fromstring(r.text))
