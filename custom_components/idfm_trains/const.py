"""Constants for the IDFM Trains integration."""

DOMAIN = "idfm_trains"

# PRIM API
PRIM_BASE_URL = "https://prim.iledefrance-mobilites.fr/marketplace"
STOP_MONITORING_URL = f"{PRIM_BASE_URL}/stop-monitoring"

# Config keys
CONF_API_KEY = "api_key"
CONF_STOP_AREA_ID = "stop_area_id"
CONF_STOP_NAME = "stop_name"
CONF_TRAIN_COUNT = "train_count"
CONF_LINES_FILTER = "lines_filter"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_OUTSIDE_INTERVAL = "outside_interval"
CONF_TIME_START = "time_start"
CONF_TIME_END = "time_end"

# Defaults
DEFAULT_STOP_NAME = "Achères-Ville"
DEFAULT_STOP_AREA_ID = "46647"  # ZdA Achères-Ville — confirmé via --list-lines
DEFAULT_TRAIN_COUNT = 5
DEFAULT_UPDATE_INTERVAL = 2     # minutes (pendant la plage active)
DEFAULT_OUTSIDE_INTERVAL = 30   # minutes (hors plage)
DEFAULT_TIME_START = "05:00"
DEFAULT_TIME_END = "23:30"

# IDs de lignes a Acheres-Ville
# Confirmes via : python test_prim_api.py --key CLE --stop 46647 --list-lines
#
# Le LineRef PRIM represente la ligne commerciale IDFM, pas la direction.
# Les deux sens (aller/retour) apparaissent sous le meme LineRef.
# La difference de volume (6 vs 37 trains) reflete la frequence de chaque ligne.
#
#   C01742 -> RER A              (Boissy-Saint-Leger <-> Cergy le Haut)
#   C01740 -> Ligne L Transilien (Paris Saint-Lazare <-> Cergy le Haut)
#
LINE_RER_A        = "C01742"
LINE_TRANSILIEN_L = "C01740"

KNOWN_LINES = {
    LINE_RER_A:        {"name": "RER A",   "color": "#E2231A"},
    LINE_TRANSILIEN_L: {"name": "Ligne L", "color": "#784786"},
}

# SIRI Lite path helpers
SIRI_ROOT             = "Siri"
SIRI_DELIVERY         = "ServiceDelivery"
SIRI_STOP_DELIVERY    = "StopMonitoringDelivery"
SIRI_MONITORED_STOP   = "MonitoredStopVisit"
SIRI_VEHICLE_JOURNEY  = "MonitoredVehicleJourney"
SIRI_MONITORED_CALL   = "MonitoredCall"
