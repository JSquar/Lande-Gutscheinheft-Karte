"""
Visualisiert Flugplätze aus flugplatzliste.txt auf einer interaktiven Karte.
Benötigt: pip install folium geopy
"""

import json
import os
import time
from pathlib import Path

import folium
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

LISTE_DATEI = Path(__file__).parent / "flugplatzliste_2026.txt"
CACHE_DATEI = Path(__file__).parent / "geocode_cache.json"
AUSGABE_KARTE = Path(__file__).parent / "flugplaetze_karte.html"

# Länderkürzel aus der Liste → Länderbezeichnung für bessere Geocoding-Ergebnisse
LAENDER_KUERZEL = {
    "(AT)": "Österreich",
    "(DK)": "Dänemark",
    "(NED)": "Niederlande",
}


def lade_cache() -> dict:
    if CACHE_DATEI.exists():
        with open(CACHE_DATEI, encoding="utf-8") as f:
            return json.load(f)
    return {}


def speichere_cache(cache: dict) -> None:
    with open(CACHE_DATEI, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def parse_flugplatz(zeile: str) -> tuple[str, str]:
    """Gibt (Anzeigename, Suchname) zurück."""
    name = zeile.strip()
    land = "Deutschland"
    for kuerzel, land_name in LAENDER_KUERZEL.items():
        if kuerzel in name:
            land = land_name
            name_clean = name.replace(kuerzel, "").strip()
            return name, f"Flugplatz {name_clean}, {land_name}"
    return name, f"Flugplatz {name}, {land}"


def geocodiere(geolocator: Nominatim, cache: dict, anzeige: str, suchname: str):
    """Sucht Koordinaten, erst mit Cache, dann per API."""
    if anzeige in cache:
        return cache[anzeige]

    versuche = [
        suchname,
        anzeige,  # Fallback: Roher Name
    ]

    for versuch in versuche:
        try:
            location = geolocator.geocode(versuch, timeout=10)
            time.sleep(1.1)  # Nominatim-Nutzungsbedingungen: max 1 req/s
            if location:
                result = {
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "adresse": location.address,
                }
                cache[anzeige] = result
                return result
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"  Fehler bei '{versuch}': {e}")
            time.sleep(2)

    print(f"  ⚠  Nicht gefunden: {anzeige}")
    cache[anzeige] = None
    return None


def erstelle_karte(flugplaetze: list[dict]) -> None:
    """Erstellt eine Folium-Karte mit allen gefundenen Flugplätzen."""
    gefundene = [f for f in flugplaetze if f["coords"]]
    lats = [f["coords"]["lat"] for f in gefundene]
    lons = [f["coords"]["lon"] for f in gefundene]

    karte = folium.Map(
        location=[sum(lats) / len(lats), sum(lons) / len(lons)],
        zoom_start=6,
        tiles="OpenStreetMap",
    )

    folium.TileLayer(
        tiles="https://snapshots.openflightmaps.org/live/2205/tiles/latest/aero/mercator/{z}/{x}/{y}.png",
        attr='© <a href="https://www.openflightmaps.org">openflightmaps</a>',
        name="ICAO (OpenFlightMaps)",
        max_zoom=11,
    ).add_to(karte)

    folium.LayerControl().add_to(karte)

    # Flugzeug-Icon-Cluster wäre schöner, aber ohne Plugin reichen einfache Marker
    for fp in gefundene:
        folium.Marker(
            location=[fp["coords"]["lat"], fp["coords"]["lon"]],
            popup=folium.Popup(
                f"<b>{fp['name']}</b><br><small>{fp['coords']['adresse']}</small>",
                max_width=300,
            ),
            tooltip=fp["name"],
            icon=folium.Icon(color="blue", icon="plane", prefix="fa"),
        ).add_to(karte)

    karte.save(AUSGABE_KARTE)


def main():
    if not LISTE_DATEI.exists():
        print(f"Datei nicht gefunden: {LISTE_DATEI}")
        return

    zeilen = [
        z.strip()
        for z in LISTE_DATEI.read_text(encoding="utf-8").splitlines()
        if z.strip()
    ]
    print(f"{len(zeilen)} Flugplätze geladen.")

    cache = lade_cache()
    geolocator = Nominatim(user_agent="aeroport_mapping_v1")

    flugplaetze = []
    for i, zeile in enumerate(zeilen, 1):
        anzeige, suchname = parse_flugplatz(zeile)
        print(f"[{i}/{len(zeilen)}] {anzeige} ...", end=" ")
        coords = geocodiere(geolocator, cache, anzeige, suchname)
        if coords:
            print(f"({coords['lat']:.4f}, {coords['lon']:.4f})")
        else:
            print("nicht gefunden")
        flugplaetze.append({"name": anzeige, "coords": coords})

    speichere_cache(cache)

    gefunden = sum(1 for f in flugplaetze if f["coords"])
    nicht_gefunden = [f["name"] for f in flugplaetze if not f["coords"]]

    print(f"\n{gefunden}/{len(flugplaetze)} Flugplätze geocodiert.")
    if nicht_gefunden:
        print("Nicht gefunden:")
        for name in nicht_gefunden:
            print(f"  - {name}")

    erstelle_karte(flugplaetze)
    print(f"\nKarte gespeichert: {AUSGABE_KARTE}")


if __name__ == "__main__":
    main()
