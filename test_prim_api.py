#!/usr/bin/env python3
"""
test_prim_api.py
────────────────
Script de test local pour l'API PRIM (Île-de-France Mobilités).
Affiche les prochains passages à Achères-Ville dans le terminal,
comme un tableau de départs en gare.

Usage :
    python test_prim_api.py --key VOTRE_CLE_API
    python test_prim_api.py --key VOTRE_CLE_API --stop 70640
    python test_prim_api.py --key VOTRE_CLE_API --raw        # dump JSON brut
    python test_prim_api.py --key VOTRE_CLE_API --line C01728 # filtrer RER A

Dépendances (stdlib uniquement, pas de pip nécessaire) :
    Python 3.8+  →  urllib, json, datetime (tout en stdlib)
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta


# ── Configuration ────────────────────────────────────────────
PRIM_URL = "https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring"

# Achères-Ville – ZdA ID (à vérifier si les données ne remontent pas)
DEFAULT_STOP_AREA_ID = "70640"

KNOWN_LINES = {
    "C01728": {"name": "RER A",    "color": "\033[91m"},   # rouge
    "C01727": {"name": "Ligne L",  "color": "\033[95m"},   # violet
}
RESET = "\033[0m"
BOLD  = "\033[1m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
RED    = "\033[91m"
GREY   = "\033[90m"


# ── Helpers ──────────────────────────────────────────────────

def parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def fmt_time(dt: datetime | None) -> str:
    if dt is None:
        return "  --:--  "
    local = dt.astimezone()
    return local.strftime("%H:%M:%S")


def minutes_from_now(dt: datetime | None) -> str:
    if dt is None:
        return "  ?"
    now = datetime.now(tz=timezone.utc)
    delta = (dt - now).total_seconds()
    if delta < 0:
        return f"{GREY}passé{RESET}"
    m = int(delta // 60)
    s = int(delta % 60)
    if m == 0:
        return f"{RED}{BOLD}imminent ({s}s){RESET}"
    if m <= 3:
        return f"{RED}{BOLD}{m} min{RESET}"
    if m <= 8:
        return f"{YELLOW}{m} min{RESET}"
    return f"{GREEN}{m} min{RESET}"


def get_line_id(line_ref: str | None) -> str | None:
    if not line_ref:
        return None
    for part in reversed(line_ref.split(":")):
        if part.startswith("C") and len(part) > 1:
            return part
    return None


# ── Appel API ────────────────────────────────────────────────

def fetch_stop_monitoring(api_key: str, stop_area_id: str) -> dict:
    monitoring_ref = f"STIF:StopArea:SP:{stop_area_id}:"
    params = urllib.parse.urlencode({"MonitoringRef": monitoring_ref})
    url = f"{PRIM_URL}?{params}"

    req = urllib.request.Request(
        url,
        headers={
            "apiKey": api_key,
            "Accept": "application/json",
        },
    )

    print(f"\n{BOLD}🔗 Requête :{RESET} {url}")
    print(f"{BOLD}🏷  MonitoringRef :{RESET} {monitoring_ref}\n")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(f"{RED}❌ HTTP 401 – Clé API invalide ou non souscrite à l'API 'Prochains passages'.{RESET}")
            sys.exit(1)
        elif e.code == 404:
            print(f"{RED}❌ HTTP 404 – Zone d'arrêt introuvable (ID: {stop_area_id}).{RESET}")
            sys.exit(1)
        elif e.code == 429:
            print(f"{RED}❌ HTTP 429 – Quota journalier dépassé.{RESET}")
            sys.exit(1)
        else:
            print(f"{RED}❌ HTTP {e.code} – {e.reason}{RESET}")
            sys.exit(1)
    except urllib.error.URLError as e:
        print(f"{RED}❌ Erreur réseau : {e.reason}{RESET}")
        sys.exit(1)

    print(f"✅ HTTP {status} – Réponse reçue ({len(raw)} octets)\n")
    return json.loads(raw)


# ── Parsing ──────────────────────────────────────────────────

def parse_departures(data: dict, line_filter: str | None = None) -> list[dict]:
    try:
        deliveries = data["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"]
    except (KeyError, TypeError):
        print(f"{RED}❌ Structure de réponse inattendue. Utilisez --raw pour inspecter.{RESET}")
        return []

    visits = []
    for delivery in deliveries:
        visits.extend(delivery.get("MonitoredStopVisit", []))

    departures = []
    now = datetime.now(tz=timezone.utc)

    for visit in visits:
        journey = visit.get("MonitoredVehicleJourney", {})
        call    = journey.get("MonitoredCall", {})

        # LineRef
        line_ref_val = journey.get("LineRef", {})
        line_ref = line_ref_val.get("value", "") if isinstance(line_ref_val, dict) else str(line_ref_val)
        line_id  = get_line_id(line_ref)

        if line_filter and line_id != line_filter:
            continue

        # Destination
        dest_list = journey.get("DestinationName", [])
        if dest_list and isinstance(dest_list, list):
            destination = dest_list[0].get("value", "?")
        else:
            destination = "?"

        # Heures
        aimed_dep    = parse_time(call.get("AimedDepartureTime")    or call.get("AimedArrivalTime"))
        expected_dep = parse_time(call.get("ExpectedDepartureTime") or call.get("ExpectedArrivalTime"))
        dep_time     = expected_dep or aimed_dep

        if dep_time is None or dep_time < now - timedelta(minutes=2):
            continue

        # Retard
        delay = 0
        if aimed_dep and expected_dep:
            delay = max(0, int((expected_dep - aimed_dep).total_seconds() / 60))

        # Quai / voie
        platform_raw = call.get("DeparturePlatformName", {})
        platform = platform_raw.get("value", "") if isinstance(platform_raw, dict) else str(platform_raw or "")

        # Numéro de course
        framed = journey.get("FramedVehicleJourneyRef", {})
        train_no = framed.get("DatedVehicleJourneyRef", "") if isinstance(framed, dict) else ""

        # Statut
        status = call.get("DepartureStatus", "")

        departures.append({
            "line_id":      line_id,
            "line_ref":     line_ref,
            "destination":  destination,
            "aimed":        aimed_dep,
            "expected":     expected_dep,
            "dep_time":     dep_time,
            "delay":        delay,
            "platform":     platform,
            "train_no":     train_no,
            "status":       status,
        })

    departures.sort(key=lambda d: d["dep_time"])
    return departures


# ── Affichage ─────────────────────────────────────────────────

def print_table(departures: list[dict], stop_id: str) -> None:
    now_str = datetime.now().strftime("%H:%M:%S")
    print(f"{BOLD}{'='*72}{RESET}")
    print(f"{BOLD}  🚉 Prochains passages – ZdA {stop_id}   (heure locale : {now_str}){RESET}")
    print(f"{BOLD}{'='*72}{RESET}")

    if not departures:
        print(f"\n{YELLOW}  ⚠️  Aucun passage trouvé.{RESET}")
        print("  → Vérifiez l'ID de zone d'arrêt avec --stop <ID>")
        print("  → Consultez https://prim.iledefrance-mobilites.fr (carte périmètre)\n")
        return

    header = f"  {'LIGNE':<10} {'DESTINATION':<30} {'THÉORIQUE':>9} {'PRÉVUE':>9} {'RETARD':>7}  {'DANS':>10}  {'VOIE':<5}"
    print(f"{BOLD}{header}{RESET}")
    print(f"  {'-'*68}")

    for dep in departures:
        line_id   = dep["line_id"] or "?"
        line_info = KNOWN_LINES.get(line_id, {"name": line_id or "?", "color": ""})
        color     = line_info["color"]
        name      = line_info["name"]

        delay_str = ""
        if dep["delay"] > 0:
            delay_str = f"{RED}+{dep['delay']} min{RESET}"
        elif dep["delay"] == 0 and dep["expected"]:
            delay_str = f"{GREEN}à l'heure{RESET}"

        row = (
            f"  {color}{BOLD}{name:<10}{RESET}"
            f" {dep['destination']:<30}"
            f" {fmt_time(dep['aimed']):>9}"
            f" {fmt_time(dep['expected']):>9}"
            f"  {delay_str:<18}"
            f" {minutes_from_now(dep['dep_time']):>10}"
            f"  {dep['platform']:<5}"
        )
        print(row)

    print(f"\n  {GREY}Données : PRIM / Île-de-France Mobilités  |  {len(departures)} départs trouvés{RESET}\n")


def print_line_ids(data: dict, stop_id: str) -> None:
    """Extrait et affiche tous les LineRef uniques présents dans la réponse API."""
    try:
        deliveries = data["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"]
    except (KeyError, TypeError):
        print(f"{RED}❌ Structure inattendue.{RESET}")
        return

    lines: dict = {}  # line_id -> {line_ref, pub_name, destinations, count}

    for delivery in deliveries:
        for visit in delivery.get("MonitoredStopVisit", []):
            journey = visit.get("MonitoredVehicleJourney", {})

            line_ref_val = journey.get("LineRef", {})
            line_ref = line_ref_val.get("value", "") if isinstance(line_ref_val, dict) else str(line_ref_val)
            line_id  = get_line_id(line_ref) or line_ref

            dest_list = journey.get("DestinationName", [])
            dest = dest_list[0].get("value", "?") if dest_list else "?"

            pub_name_val = journey.get("PublishedLineName", [])
            pub_name = pub_name_val[0].get("value", "") if pub_name_val else ""

            if line_id not in lines:
                lines[line_id] = {"line_ref": line_ref, "pub_name": pub_name, "destinations": set(), "count": 0}
            lines[line_id]["destinations"].add(dest)
            lines[line_id]["count"] += 1

    print(f"\n{BOLD}{'='*65}{RESET}")
    print(f"{BOLD}  🔍 LineRef présents pour ZdA {stop_id}{RESET}")
    print(f"{BOLD}{'='*65}{RESET}\n")

    if not lines:
        print(f"  {YELLOW}Aucune ligne trouvée dans la réponse.{RESET}\n")
        return

    print(f"  {'CODE':>10}  {'NOM PUBLIÉ':<18}  {'DESTINATIONS':<35}  TRAINS")
    print(f"  {'-'*75}")
    for line_id, info in sorted(lines.items()):
        dests = ", ".join(sorted(info["destinations"]))[:35]
        name  = info["pub_name"] or "?"
        print(f"  {BOLD}{line_id:>10}{RESET}  {name:<18}  {dests:<35}  {info['count']}")

    print(f"\n  {GREY}LineRef STIF complet :{RESET}")
    for line_id, info in sorted(lines.items()):
        print(f"    {line_id}  →  {info['line_ref']}")

    print(f"\n  {BOLD}💡 Copiez le CODE et utilisez-le avec --line pour filtrer.{RESET}")
    first_id = next(iter(lines))
    print(f"     Ex : python test_prim_api.py --key CLE --stop {stop_id} --line {first_id}\n")


def print_diagnostics(data: dict, stop_id: str) -> None:
    """Affiche des infos de diagnostic si aucun départ n'est trouvé."""
    print(f"\n{BOLD}🔍 Diagnostic{RESET}")
    try:
        deliveries = data["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"]
        total_visits = sum(len(d.get("MonitoredStopVisit", [])) for d in deliveries)
        print(f"  MonitoredStopVisit reçus (bruts) : {total_visits}")
        if total_visits > 0:
            # Montre les LineRef présents
            line_refs = set()
            for d in deliveries:
                for v in d.get("MonitoredStopVisit", []):
                    lr = v.get("MonitoredVehicleJourney", {}).get("LineRef", {})
                    line_refs.add(lr.get("value", "?") if isinstance(lr, dict) else str(lr))
            print(f"  LineRef présents dans la réponse :")
            for lr in sorted(line_refs):
                lid = get_line_id(lr)
                known = KNOWN_LINES.get(lid, {})
                tag = f" ← {known['name']}" if known else ""
                print(f"    • {lr}{tag}")
    except (KeyError, TypeError) as e:
        print(f"  {RED}Impossible de parser la réponse : {e}{RESET}")


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Teste l'API PRIM – affiche les prochains passages en gare."
    )
    parser.add_argument("--key",   required=True, help="Clé API PRIM")
    parser.add_argument("--stop",  default=DEFAULT_STOP_AREA_ID,
                        help=f"ID Zone d'arrêt ZdA (défaut : {DEFAULT_STOP_AREA_ID} = Achères-Ville)")
    parser.add_argument("--line",  default=None,
                        help="Filtrer par ligne (utiliser le code extrait avec --list-lines)")
    parser.add_argument("--list-lines", action="store_true",
                        help="Lister tous les LineRef présents dans la réponse (pour trouver les bons codes)")
    parser.add_argument("--raw",   action="store_true",
                        help="Afficher le JSON brut complet (pour déboguer)")
    parser.add_argument("--raw-first", action="store_true",
                        help="Afficher uniquement le 1er MonitoredStopVisit (JSON)")
    args = parser.parse_args()

    data = fetch_stop_monitoring(args.key, args.stop)

    if args.raw:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    if args.raw_first:
        try:
            first = data["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"][0]["MonitoredStopVisit"][0]
            print(json.dumps(first, indent=2, ensure_ascii=False))
        except (KeyError, IndexError):
            print("Aucun MonitoredStopVisit dans la réponse.")
        return

    if args.list_lines:
        print_line_ids(data, args.stop)
        return

    departures = parse_departures(data, line_filter=args.line)
    print_table(departures, args.stop)

    if not departures:
        print_diagnostics(data, args.stop)


if __name__ == "__main__":
    main()
