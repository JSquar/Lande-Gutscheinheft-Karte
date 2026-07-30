"""
Visualisiert Flugplätze aus flugplatzliste_YYYY.txt auf einer interaktiven Karte.
Alle gefundenen Jahresdateien werden als separate Layer eingebunden.
Benötigt: pip install folium geopy
"""

import datetime
import json
import time
from pathlib import Path

import folium
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

VERZEICHNIS = Path(__file__).parent
FLUGPLATZ_LISTEN_DIR = VERZEICHNIS / "data"
CACHE_DATEI = VERZEICHNIS / "geocode_cache.json"
AUSGABE_KARTE = VERZEICHNIS / "dist" / "index.html"
AKTUELLES_JAHR = datetime.date.today().year

# Länderkürzel aus der Liste → Länderbezeichnung für bessere Geocoding-Ergebnisse
LAENDER_KUERZEL = {
    "(AT)": "Österreich",
    "(DK)": "Dänemark",
    "(NED)": "Niederlande",
}

# Häufige Schreibvarianten aus der Liste -> besser geocodierbare Form
NAMENS_KORREKTUREN = {
    "Ringstedt": "Ringsted",
    "Dermstorf": "Dermsdorf",
}

# Gezielt zusätzliche Suchanfragen für schwer auffindbare Plätze
SONDER_SUCHANFRAGEN = {
    "Rheine - Eschensdorf": [
        "Rheine-Eschendorf, Germany",
        "Flugplatz Rheine Eschendorf, Germany",
    ],
    "Ringstedt (DK)": [
        "Ringsted Flyveplads, Denmark",
        "Ringsted, Denmark",
    ],
    "Schweighofen - Wissembourg": [
        "Aérodrome de Wissembourg, France",
        "Schweighofen, Rheinland-Pfalz, Germany",
    ],
    "Sömmerda - Dermstorf": [
        "Dermsdorf, Sömmerda, Germany",
        "Flugplatz Sömmerda Dermsdorf, Germany",
    ],
    "Texel (NED)": [
        "Texel International Airport, Netherlands",
        "EHTX, Netherlands",
    ],
}


def normalisiere_name(name: str) -> str:
    result = name
    for falsch, korrekt in NAMENS_KORREKTUREN.items():
        result = result.replace(falsch, korrekt)
    return result


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
    name_norm = normalisiere_name(name)
    land = "Deutschland"
    for kuerzel, land_name in LAENDER_KUERZEL.items():
        if kuerzel in name_norm:
            land = land_name
            name_clean = name_norm.replace(kuerzel, "").strip()
            return name, f"Flugplatz {name_clean}, {land_name}"
    return name, f"Flugplatz {name_norm}, {land}"


def geocodiere(geolocator: Nominatim, cache: dict, anzeige: str, suchname: str):
    """Sucht Koordinaten, erst mit Cache, dann per API."""
    if anzeige in cache and cache[anzeige] is not None:
        return cache[anzeige]

    if anzeige in cache and cache[anzeige] is None:
        print("(erneuter Versuch) ", end="")

    versuche = SONDER_SUCHANFRAGEN.get(anzeige, []) + [
        suchname,
        normalisiere_name(anzeige),
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


def finde_jahresdateien() -> dict[int, Path]:
    """Gibt {Jahr: Path} zurück, sortiert nach Jahr aufsteigend."""
    result = {}
    for p in sorted(FLUGPLATZ_LISTEN_DIR.glob("flugplatzliste_*.txt")):
        try:
            jahr = int(p.stem.rsplit("_", 1)[-1])
            result[jahr] = p
        except ValueError:
            pass
    return result


def erstelle_karte(jahre_daten: dict[int, list[dict]]) -> None:
    """Erstellt eine Folium-Karte mit einem Layer pro Jahr.

    Das aktuelle Jahr ist standardmäßig eingeblendet, ältere Jahre ausgeblendet.
    """
    alle_coords = [
        fp["coords"] for fps in jahre_daten.values() for fp in fps if fp["coords"]
    ]
    if not alle_coords:
        print("Keine Koordinaten gefunden – Karte wird nicht erstellt.")
        return

    lats = [c["lat"] for c in alle_coords]
    lons = [c["lon"] for c in alle_coords]

    karte = folium.Map(
        location=[sum(lats) / len(lats), sum(lons) / len(lons)],
        zoom_start=6,
        tiles="OpenStreetMap",
    )

    for jahr, flugplaetze in sorted(jahre_daten.items(), reverse=True):
        ist_aktuell = jahr == AKTUELLES_JAHR
        gruppe = folium.FeatureGroup(
            name=str(jahr),
            show=ist_aktuell,
        )
        gefundene = [f for f in flugplaetze if f["coords"]]
        farbe = "blue" if ist_aktuell else "gray"
        for fp in gefundene:
            folium.Marker(
                location=[fp["coords"]["lat"], fp["coords"]["lon"]],
                popup=folium.Popup(
                    f"<b>{fp['name']}</b><br><small>{fp['coords']['adresse']}</small>",
                    max_width=300,
                ),
                tooltip=f"{fp['name']} ({jahr})",
                icon=folium.Icon(color=farbe, icon="plane", prefix="fa"),
            ).add_to(gruppe)
        gruppe.add_to(karte)

    folium.LayerControl(collapsed=False).add_to(karte)

    AUSGABE_KARTE.parent.mkdir(parents=True, exist_ok=True)
    karte.save(AUSGABE_KARTE)


def main():
    jahresdateien = finde_jahresdateien()
    if not jahresdateien:
        print("Keine Jahresdateien (flugplatzliste_YYYY.txt) gefunden.")
        return

    jahre_str = ", ".join(str(j) for j in sorted(jahresdateien))
    print(f"Gefundene Jahre: {jahre_str}")

    cache = lade_cache()
    geolocator = Nominatim(user_agent="aeroport_mapping_v1")

    jahre_daten: dict[int, list[dict]] = {}
    for jahr, datei in sorted(jahresdateien.items()):
        zeilen = [
            z.strip()
            for z in datei.read_text(encoding="utf-8").splitlines()
            if z.strip()
        ]
        print(f"\n── {jahr}: {len(zeilen)} Flugplätze ──")
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
        jahre_daten[jahr] = flugplaetze

    speichere_cache(cache)

    for jahr, flugplaetze in jahre_daten.items():
        gefunden = sum(1 for f in flugplaetze if f["coords"])
        nicht_gefunden = [f["name"] for f in flugplaetze if not f["coords"]]
        print(f"\n{jahr}: {gefunden}/{len(flugplaetze)} geocodiert.")
        if nicht_gefunden:
            print("  Nicht gefunden:")
            for name in nicht_gefunden:
                print(f"    - {name}")

    erstelle_karte(jahre_daten)
    print(f"\nKarte gespeichert: {AUSGABE_KARTE}")


if __name__ == "__main__":
    main()
