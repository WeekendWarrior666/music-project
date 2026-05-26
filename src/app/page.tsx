"use client";

import { useEffect, useState } from "react";
import bandsData from "../../data.json";

type Album = { title: string; mbid: string; artwork: string };
type Tour = { city: string; date: string; venue?: string };
type Band = { name: string; genre: string; albums: Album[]; tours: Tour[] };

const defaultBands = bandsData as Band[];

const BASE_URL = "https://musicbrainz.org/ws/2";

async function fetchBandData(name: string): Promise<Band | null> {
  try {
    const encoded = encodeURIComponent(name);

    // Search for artist
    const artistRes = await fetch(
      `${BASE_URL}/artist/?query=artist:${encoded}&fmt=json`,
      { headers: { "User-Agent": "MetalSiteProject/1.0" } }
    );
    const artistData = await artistRes.json();
    const artist = artistData.artists?.[0];
    if (!artist) return null;

    // Get genre from tags
    const tags = artist.tags ?? [];
    const topTag = tags.sort((a: any, b: any) => b.count - a.count)[0];
    const genre = topTag ? topTag.name.charAt(0).toUpperCase() + topTag.name.slice(1) : "Metal";

    // Get top 3 albums
    const albumRes = await fetch(
      `${BASE_URL}/release-group?artist=${artist.id}&type=album&fmt=json&limit=3`,
      { headers: { "User-Agent": "MetalSiteProject/1.0" } }
    );
    const albumData = await albumRes.json();
    const albums: Album[] = (albumData["release-groups"] ?? []).slice(0, 3).map((rg: any) => ({
      title: rg.title,
      mbid: rg.id,
      artwork: `https://coverartarchive.org/release-group/${rg.id}/front`,
    }));

    return { name: artist.name, genre, albums, tours: [] };
  } catch (e) {
    return null;
  }
}

function TracklistModal({ album, onClose }: { album: Album | null; onClose: () => void }) {
  const [tracks, setTracks] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!album) return;
    setLoading(true);
    setTracks([]);

    fetch(`https://musicbrainz.org/ws/2/release?release-group=${album.mbid}&fmt=json&limit=1`, {
      headers: { "User-Agent": "MetalSiteProject/1.0" },
    })
      .then((r) => r.json())
      .then((data) => {
        const releaseId = data.releases?.[0]?.id;
        if (!releaseId) {
          setLoading(false);
          return;
        }
        return fetch(
          `https://musicbrainz.org/ws/2/release/${releaseId}?inc=recordings&fmt=json`,
          { headers: { "User-Agent": "MetalSiteProject/1.0" } }
        );
      })
      .then((r) => r?.json())
      .then((data) => {
        const media = data?.media?.[0];
        const trackList = media?.tracks?.map((t: { title: string }) => t.title) ?? [];
        setTracks(trackList);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [album]);

  if (!album) return null;

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 px-4" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-8 max-w-md w-full max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-start gap-4 mb-6">
          <img
            src={album.artwork}
            alt={album.title}
            className="w-20 h-20 rounded object-cover bg-zinc-800"
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
          <div>
            <h2 className="text-xl font-extrabold text-white">{album.title}</h2>
            <p className="text-zinc-500 text-sm mt-1">Full Tracklist</p>
          </div>
          <button onClick={onClose} className="ml-auto text-zinc-500 hover:text-white text-2xl leading-none">✕</button>
        </div>

        {/* Tracks */}
        {loading ? (
          <p className="text-zinc-500 text-sm text-center py-4">Loading tracks...</p>
        ) : tracks.length === 0 ? (
          <p className="text-zinc-500 text-sm text-center py-4">No tracklist found.</p>
        ) : (
          <ol className="space-y-2">
            {tracks.map((track, i) => (
              <li key={i} className="flex items-center gap-3 text-sm">
                <span className="text-zinc-600 w-6 text-right">{i + 1}</span>
                <span className="text-zinc-200">{track}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function BandCard({ band, onAlbumClick }: { band: Band; onAlbumClick: (album: Album) => void }) {
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 hover:border-red-600 transition-colors duration-300">
      <h2 className="text-2xl font-extrabold uppercase tracking-tight text-white">
        {band.name}
      </h2>
      <span className="inline-block mt-1 mb-5 text-xs font-semibold uppercase tracking-widest text-red-500 bg-red-950 px-2 py-0.5 rounded">
        {band.genre}
      </span>

      {/* Albums */}
      <div className="mb-5">
        <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-2">
          Discography
        </h3>
        <ul className="space-y-3">
          {band.albums.map((album) => (
            <li key={album.title} className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity" onClick={() => onAlbumClick(album)}>
              <img
                src={album.artwork}
                alt={album.title}
                width={48}
                height={48}
                className="rounded w-12 h-12 object-cover bg-zinc-800"
                onError={(e) => { e.currentTarget.style.display = "none"; }}
              />
              <span className="text-sm text-zinc-300">{album.title}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Tour Dates */}
      {band.tours.length > 0 && (
        <div>
          <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-2">
            Tour Dates
          </h3>
          <ul className="space-y-2">
            {band.tours.map((show) => (
              <li
                key={`${show.date}-${show.city}`}
                className="flex justify-between gap-3 text-sm border border-zinc-800 rounded-lg px-3 py-2 bg-zinc-800/50"
              >
                <div className="min-w-0">
                  <span className="text-zinc-200 block truncate">{show.city}</span>
                  {show.venue && (
                    <span className="text-zinc-500 text-xs truncate block">{show.venue}</span>
                  )}
                </div>
                <span className="text-zinc-500 shrink-0">{show.date}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<Band | null>(null);
  const [loading, setLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [selectedAlbum, setSelectedAlbum] = useState<Album | null>(null);

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setNotFound(false);
    setSearchResult(null);

    const result = await fetchBandData(query.trim());

    if (result) {
      setSearchResult(result);
    } else {
      setNotFound(true);
    }
    setLoading(false);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleSearch();
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 px-6 py-16 font-sans">
      <TracklistModal album={selectedAlbum} onClose={() => setSelectedAlbum(null)} />
      {/* Header */}
      <header className="text-center mb-12">
        <h1 className="text-5xl font-black uppercase tracking-widest text-red-600 drop-shadow-lg">
          🤘 Metal Underground
        </h1>
        <p className="mt-3 text-zinc-400 text-lg tracking-wide">
          Albums · Tour Dates · Darkness
        </p>
      </header>

      {/* Search Bar */}
      <div className="max-w-xl mx-auto mb-16 flex gap-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search any band... e.g. Slayer"
          className="flex-1 bg-zinc-800 border border-zinc-600 rounded-xl px-4 py-3 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-red-600 transition-colors"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="bg-red-600 hover:bg-red-700 disabled:bg-zinc-700 text-white font-bold px-6 py-3 rounded-xl transition-colors"
        >
          {loading ? "..." : "Search"}
        </button>
      </div>

      {/* Search Result */}
      {notFound && (
        <p className="text-center text-zinc-500 mb-10">No band found for "{query}". Try another name.</p>
      )}
      {searchResult && (
        <div className="max-w-sm mx-auto mb-16">
          <p className="text-xs uppercase tracking-widest text-zinc-500 mb-4 text-center">Search Result</p>
          <BandCard band={searchResult} onAlbumClick={setSelectedAlbum} />
        </div>
      )}

      {/* Default Bands */}
      <section className="grid gap-10 max-w-5xl mx-auto md:grid-cols-3">
        {defaultBands.map((band) => (
         <BandCard key={band.name} band={band} onAlbumClick={setSelectedAlbum} />
        ))}
      </section>

      {/* Footer */}
      <footer className="text-center mt-24 text-zinc-600 text-sm tracking-wide">
        © 2026 Metal Underground · Built with Next.js & Tailwind
      </footer>
    </main>
  );
}