# agent.py
import urllib.request
import urllib.parse
import json
import time
import ssl

BASE_URL = "https://musicbrainz.org/ws/2"
HEADERS = {
    "User-Agent": "MetalSiteProject/1.0 (your@email.com)"
}

BANDS = ["Iron Maiden", "Metallica", "Black Sabbath"]

def search_artist(name):
    encoded_name = urllib.parse.quote(name)
    url = f"{BASE_URL}/artist/?query=artist:{encoded_name}&fmt=json"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as res:
        data = json.loads(res.read())
    artists = data.get("artists", [])
    if not artists:
        return None
    # Return the best match (first result)
    return artists[0]

def get_top_albums(artist_id):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    url = f"{BASE_URL}/release-group?artist={artist_id}&type=album&fmt=json&limit=3"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, context=ssl_context) as res:
        data = json.loads(res.read())
    albums = []
    for rg in data.get("release-groups", [])[:3]:
        albums.append({
            "title": rg.get("title", "Unknown"),
            "mbid": rg.get("id", ""),
            "artwork": f"https://coverartarchive.org/release-group/{rg.get('id', '')}/front"
        })
    return albums

def get_tour_dates(artist_name):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    encoded_name = urllib.parse.quote(artist_name)
    url = f"https://rest.bandsintown.com/artists/{encoded_name}/events?app_id=metal-site"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=ssl_context) as res:
            events = json.loads(res.read())
        tours = []
        for event in events[:3]:
            tours.append({
                "city": f"{event['venue']['city']}, {event['venue']['country']}",
                "date": event['datetime'][:10]
            })
        return tours
    except Exception as e:
        print(f"  Could not fetch tours for {artist_name}: {e}")
        return []

def get_genre(artist):
    # MusicBrainz stores genres as tags
    tags = artist.get("tags", [])
    if tags:
        # Sort by vote count and return top tag
        tags_sorted = sorted(tags, key=lambda t: t.get("count", 0), reverse=True)
        return tags_sorted[0]["name"].title()
    return "Metal"

def main():
    results = []

    for band_name in BANDS:
        print(f"Searching for {band_name}...")
        artist = search_artist(band_name)

        if not artist:
            print(f"  Could not find {band_name}, skipping.")
            continue

        artist_id = artist["id"]
        genre = get_genre(artist)

        print(f"  Found: {artist.get('name')} | Genre: {genre}")

        # Pause to respect MusicBrainz rate limit (1 request/sec)
        time.sleep(1)

        albums = get_top_albums(artist_id)
        print(f"  Albums: {[a['title'] for a in albums]}")

        results.append({
            "name": artist.get("name", band_name),
            "genre": genre,
            "albums": albums,
            "tours": get_tour_dates(band_name)
            
        })

        # Pause again between bands
        time.sleep(1)

    # Save to data.json
    with open("data.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n✅ Done! data.json has been saved.")

if __name__ == "__main__":
    main()