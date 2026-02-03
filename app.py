import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
from math import radians, sin, cos, sqrt, atan2
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from urllib.parse import quote_plus, urlencode
from datetime import datetime, timedelta, timezone

# =========================================================
# PitchFinder V3.6 — FULL SCRIPT (Streamlit)
# =========================================================
# ✅ "Y aller" (Apple Maps if iOS/macOS UA else Google Maps)
# ✅ "Plan a game" moved to bottom of sidebar
# ✅ Radius up to 20km (single slider; removed "use profile radius")
# ✅ Apple Calendar (.ics download) + Google Calendar link (only when plan_mode ON)
# ✅ Cards: always outlined; selected outline changes color
# ✅ Selection unique via pitch_id (fix "all selected" bug)
# ✅ Message:
#    - plan_mode OFF: no date/time/players
#    - plan_mode ON: includes date/time/players + calendars
# ✅ No key= on st.link_button (older Streamlit compatibility)
# ✅ Unique key= on st.download_button (fix DuplicateElementId)
# =========================================================


# ============================
# Session state
# ============================
def init_state():
    defaults = {
        "df_top": None,
        "selected_pitch_id": None,
        "selected_lat": None,
        "selected_lon": None,
        "folium_map": None,
        "last_error": None,
        "origin_lat": None,
        "origin_lon": None,

        # Plan defaults (editable anytime)
        "plan_mode": False,
        "plan_date": datetime.now().date(),
        "plan_time": datetime.now().replace(minute=0, second=0, microsecond=0).time(),
        "plan_players": 10,

        # User identity for message
        "user_name": "Luc",
        "user_style": "terrain",  # match or terrain

        # Sticky search defaults
        "last_address": "Bordeaux, France",
        "last_profile_name": "Walking",
        "last_pitch_type": "all",
        "last_paid_filter": "show_all",
        "last_radius_km": 5,
        "last_top_n": 10,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()

# ============================
# 1) Distance + Geocoding
# ============================
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


_geolocator = Nominatim(user_agent="pitchfinder_streamlit_v36_folium")
_geocode = RateLimiter(_geolocator.geocode, min_delay_seconds=1)


def geocode_address(address: str):
    if "france" not in address.lower():
        address = address + ", France"
    loc = _geocode(address)
    if loc is None:
        return None
    return (loc.latitude, loc.longitude)


# ============================
# 2) Overpass API (OpenStreetMap)
# ============================
def overpass_get_pitches(lat, lon, radius_m=3000):
    query = f"""
    [out:json][timeout:40];
    (
      node["leisure"="pitch"]["sport"="soccer"](around:{radius_m},{lat},{lon});
      way["leisure"="pitch"]["sport"="soccer"](around:{radius_m},{lat},{lon});
      relation["leisure"="pitch"]["sport"="soccer"](around:{radius_m},{lat},{lon});
    );
    out center tags;
    """

    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.nchc.org.tw/api/interpreter",
    ]

    last_error = None
    for url in endpoints:
        try:
            r = requests.get(url, params={"data": query}, timeout=90)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_error = e

    raise RuntimeError(f"Overpass API error (all endpoints failed). Last error: {last_error}")


# ============================
# 3) Providers + links
# ============================
def detect_provider(name: str) -> str:
    if not isinstance(name, str):
        return "Public/Other"
    n = name.lower()
    if "urbansoccer" in n or "urban soccer" in n:
        return "UrbanSoccer"
    if "le five" in n or "lefive" in n:
        return "Le Five"
    if "five" in n:
        return "Five (generic)"
    return "Public/Other"


def is_bookable_provider(provider: str) -> bool:
    return provider in ("UrbanSoccer", "Le Five")


def provider_booking_link(provider: str) -> str:
    utm = "utm_source=pitchfinder&utm_medium=referral&utm_campaign=student_project"
    if provider == "UrbanSoccer":
        return f"https://www.urbansoccer.fr/?{utm}"
    if provider == "Le Five":
        return f"https://lefive.fr/?{utm}"
    return ""


def gmaps_directions_link(origin_lat, origin_lon, dest_lat, dest_lon) -> str:
    return (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin_lat},{origin_lon}"
        f"&destination={dest_lat},{dest_lon}"
    )


def google_maps_place_link(dest_lat, dest_lon, label="Destination") -> str:
    return f"https://www.google.com/maps/search/?api=1&query={dest_lat},{dest_lon}({quote_plus(label)})"


def apple_maps_place_link(dest_lat, dest_lon, label="Destination") -> str:
    return f"https://maps.apple.com/?ll={dest_lat},{dest_lon}&q={quote_plus(label)}"


def go_button_html(dest_lat, dest_lon, label, element_id):
    g = google_maps_place_link(dest_lat, dest_lon, label)
    a = apple_maps_place_link(dest_lat, dest_lon, label)
    safe_label = (label or "Destination").replace('"', "'")

    return f"""
    <button id="{element_id}" style="
        width:100%;
        padding:8px 12px;
        border-radius:12px;
        border:1px solid rgba(0,0,0,0.18);
        background: rgba(255,255,255,0.55);
        cursor:pointer;
    ">🧭 Y aller</button>
    <script>
      (function() {{
        const btn = document.getElementById("{element_id}");
        const ua = navigator.userAgent || "";
        const isApple = /iPhone|iPad|iPod|Macintosh/.test(ua);
        const appleUrl = "{a}";
        const googleUrl = "{g}";

        btn.onclick = () => {{
          const url = isApple ? appleUrl : googleUrl;
          window.open(url, "_blank");
        }};
        btn.title = "Ouvre {safe_label} dans Apple Maps si possible, sinon Google Maps";
      }})();
    </script>
    """


# ============================
# 4) Build DataFrame
# ============================
def pitches_to_df(osm_json, user_lat, user_lon):
    rows = []
    for el in osm_json.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name", "Unnamed pitch")

        surface = tags.get("surface", "").lower()
        access = tags.get("access", "").lower()
        fee = tags.get("fee", "").lower()
        indoor = tags.get("indoor", "").lower()

        if el.get("type") == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")

        if lat is None or lon is None:
            continue

        dist = haversine_km(user_lat, user_lon, lat, lon)

        rows.append({
            "name": name,
            "distance_km": dist,
            "surface": surface,
            "access": access,
            "fee": fee,
            "indoor": indoor,
            "lat": float(lat),
            "lon": float(lon),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["distance_km"] = df["distance_km"].round(2)
    df["provider"] = df["name"].apply(detect_provider)

    # ✅ Unique ID prevents multiple selection bug
    df["pitch_id"] = df.apply(lambda r: f"{r['lat']:.6f},{r['lon']:.6f}", axis=1)

    return df.sort_values("distance_km").reset_index(drop=True)


# ============================
# 5) Filters
# ============================
def filter_by_pitch_type(df, pitch_type):
    pitch_type = (pitch_type or "all").lower().strip()

    if pitch_type == "grass":
        return df[df["surface"].str.contains("grass|gazon", na=False)]
    if pitch_type == "clay":
        return df[df["surface"].str.contains("clay|sand|dirt|terre", na=False)]
    if pitch_type == "synthetic":
        return df[df["surface"].str.contains("artificial|synthetic|turf|rubber|artificial_turf", na=False)]
    if pitch_type == "city":
        return df[
            (df["indoor"].str.contains("yes", na=False)) |
            (df["name"].str.lower().str.contains("five|city|urban", na=False))
        ]
    return df


def apply_paid_filter(df, paid_filter="show_all"):
    paid_filter = (paid_filter or "show_all").lower().strip()
    if paid_filter == "hide_paid":
        return df[~df["fee"].str.contains("yes|true", na=False)]
    return df


# ============================
# 6) Profiles + ETA + Score
# ============================
PROFILES = {
    "Walking": {"mode": "walk", "prefer": ["city", "synthetic"]},
    "Student Budget": {"mode": "walk", "prefer": ["grass", "synthetic"]},
    "Car": {"mode": "car", "prefer": ["grass", "synthetic"]},
}
SPEED_KMH = {"walk": 5, "car": 30}


def add_eta_minutes(df, mode):
    speed = SPEED_KMH.get(mode, 5)
    out = df.copy()
    out["eta_min"] = (out["distance_km"] / speed * 60).round(0).astype(int)
    return out


def add_recommendation_score(df, profile_name, pitch_type_selected):
    profile = PROFILES[profile_name]
    prefer = profile.get("prefer", [])

    out = df.copy()
    out["score_raw"] = 100.0
    out["score_raw"] -= out["distance_km"] * 10

    pt = (pitch_type_selected or "all").lower().strip()
    if pt != "all":
        if pt == "grass":
            out.loc[out["surface"].str.contains("grass|gazon", na=False), "score_raw"] += 6
        elif pt == "synthetic":
            out.loc[out["surface"].str.contains("artificial|synthetic|turf|rubber|artificial_turf", na=False), "score_raw"] += 6
        elif pt == "clay":
            out.loc[out["surface"].str.contains("clay|sand|dirt|terre", na=False), "score_raw"] += 6
        elif pt == "city":
            out.loc[
                (out["indoor"].str.contains("yes", na=False)) |
                (out["name"].str.lower().str.contains("five|city|urban", na=False)),
                "score_raw"
            ] += 6

    for p in prefer:
        if p == "grass":
            out.loc[out["surface"].str.contains("grass|gazon", na=False), "score_raw"] += 4
        if p == "synthetic":
            out.loc[out["surface"].str.contains("artificial|synthetic|turf|rubber|artificial_turf", na=False), "score_raw"] += 4
        if p == "city":
            out.loc[
                (out["indoor"].str.contains("yes", na=False)) |
                (out["name"].str.lower().str.contains("five|city|urban", na=False)),
                "score_raw"
            ] += 4

    out.loc[out["fee"].str.contains("yes|true", na=False), "score_raw"] -= 15
    out["score_raw"] = out["score_raw"].clip(lower=0, upper=100).round(1)
    out["stars5"] = (out["score_raw"] / 20).round().clip(lower=0, upper=5).astype(int)
    return out


def profile_mode_label(profile_name: str) -> str:
    # You asked: show "car" / "walk" (not the profile name)
    return PROFILES.get(profile_name, {}).get("mode", (profile_name or "").lower()).lower()


# ============================
# 7) Share + Calendar helpers
# ============================
def stars_txt(n: int) -> str:
    n = max(0, min(5, int(n)))
    return "⭐" * n + "☆" * (5 - n)


def format_share_message(
    user_name,
    user_style,
    plan_mode,
    name,
    stars5,
    profile_name,
    dist_km,
    eta_min,
    directions_url,
    date_=None,
    time_=None,
    players=None
):
    intro = f"{user_name} a préparé le match ⚽" if user_style == "match" else f"{user_name} a préparé le terrain 🏟️"
    stars_line = stars_txt(stars5)
    prof = profile_mode_label(profile_name)

    if not plan_mode:
        return (
            f"{intro}\n\n"
            f"📍 {name}\n"
            f"⭐ Rating: {stars_line}\n"
            f"🚗 Profil: {prof}\n"
            f"📏 {dist_km} km • ⏱ ~{eta_min} min\n"
            f"🧭 Itinéraire: {directions_url}\n"
        )

    return (
        f"{intro}\n\n"
        f"📍 {name}\n"
        f"⭐ Rating: {stars_line}\n"
        f"🗓 {date_} • 🕒 {time_}\n"
        f"👥 {players} joueurs\n"
        f"🚗 Profil: {prof}\n"
        f"📏 {dist_km} km • ⏱ ~{eta_min} min\n"
        f"🧭 Itinéraire: {directions_url}\n"
    )


def google_calendar_link(title, start_dt, end_dt, details, location=""):
    start_utc = start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end_utc = end_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start_utc}/{end_utc}",
        "details": details,
        "location": location,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def build_ics_event(title, start_dt, end_dt, description, location=""):
    def esc(s: str) -> str:
        return (s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dtstart = start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dtend = end_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    uid = f"pitchfinder-{int(datetime.now().timestamp())}@local"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PitchFinder//V3.6//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{esc(title)}",
        f"DESCRIPTION:{esc(description)}",
        f"LOCATION:{esc(location)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


def copy_button(text: str, key: str, label: str = "Copier le message"):
    safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    components.html(
        f"""
        <button id="{key}" style="
            width:100%;
            padding:8px 12px;
            border-radius:12px;
            border:1px solid rgba(0,0,0,0.18);
            background: rgba(255,255,255,0.55);
            cursor:pointer;
        ">{label}</button>
        <script>
        const btn = document.getElementById("{key}");
        btn.onclick = async () => {{
            try {{
                await navigator.clipboard.writeText(`{safe}`);
                btn.innerText = "Copié ✅";
                setTimeout(() => btn.innerText = "{label}", 1200);
            }} catch (e) {{
                btn.innerText = "Copie impossible";
                setTimeout(() => btn.innerText = "{label}", 1200);
            }}
        }};
        </script>
        """,
        height=55
    )


# ============================
# 8) Map (highlight selected + center/zoom)
# ============================
def make_map(user_lat, user_lon, df_top, radius_km, selected_id=None, selected_lat=None, selected_lon=None):
    if selected_lat is not None and selected_lon is not None:
        m = folium.Map(location=[selected_lat, selected_lon], zoom_start=16, control_scale=True)
    else:
        m = folium.Map(location=[user_lat, user_lon], zoom_start=13, control_scale=True)

    folium.Circle(
        location=[user_lat, user_lon],
        radius=int(radius_km * 1000),
        fill=False
    ).add_to(m)

    folium.Marker(
        [user_lat, user_lon],
        tooltip="Your location",
        popup="Origin",
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(m)

    for _, row in df_top.iterrows():
        is_selected = (selected_id is not None and row["pitch_id"] == selected_id)
        directions = gmaps_directions_link(user_lat, user_lon, row["lat"], row["lon"])
        provider = row.get("provider", "Public/Other")

        popup = (
            f"<b>{row['name']}</b><br>"
            f"Provider: {provider}<br>"
            f"Distance: {row['distance_km']} km<br>"
            f"ETA: {row.get('eta_min','?')} min<br>"
            f"Surface: {row.get('surface','') or 'n/a'}<br>"
            f"Fee tag: {row.get('fee','') or 'unknown'}<br><br>"
            f"<a href='{directions}' target='_blank'>Directions (Google Maps)</a>"
        )

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=10 if is_selected else 7,
            color="#ff8c00" if is_selected else "#9e9e9e",
            fill=True,
            fill_color="#ff8c00" if is_selected else "#9e9e9e",
            fill_opacity=0.95 if is_selected else 0.75,
            tooltip=row["name"],
            popup=popup,
        ).add_to(m)

    return m


# ============================
# 9) UI
# ============================
st.set_page_config(page_title="PitchFinder", page_icon="⚽", layout="wide")

st.markdown(
    """
    <div style="display:flex; align-items:baseline; gap:12px;">
      <h1 style="margin:0;">⚽ PitchFinder</h1>
      <span style="opacity:0.75;">Find & plan football games around any address</span>
    </div>
    """,
    unsafe_allow_html=True
)
st.caption("ETA = Estimated Travel Time (minutes), based on your selected profile (walk/car).")

# Sidebar
with st.sidebar:
    st.header("Search")

    with st.expander("👤 Profil utilisateur", expanded=True):
        st.session_state.user_name = st.text_input("Ton prénom", value=st.session_state.user_name)
        st.session_state.user_style = st.selectbox(
            "Style du message",
            ["match", "terrain"],
            index=0 if st.session_state.user_style == "match" else 1
        )

    # --- Search form (Plan moved to bottom, outside the form) ---
    with st.form("search_form"):
        address = st.text_input("Address", value=st.session_state.last_address)

        profile_name = st.selectbox(
            "Profile",
            options=list(PROFILES.keys()),
            index=list(PROFILES.keys()).index(st.session_state.last_profile_name)
            if st.session_state.last_profile_name in PROFILES else 0
        )
        pitch_type = st.selectbox(
            "Pitch type",
            ["all", "grass", "clay", "synthetic", "city"],
            index=["all", "grass", "clay", "synthetic", "city"].index(st.session_state.last_pitch_type)
            if st.session_state.last_pitch_type in ["all", "grass", "clay", "synthetic", "city"] else 0
        )
        paid_filter = st.selectbox(
            "Paid pitches",
            ["show_all", "hide_paid"],
            index=["show_all", "hide_paid"].index(st.session_state.last_paid_filter)
            if st.session_state.last_paid_filter in ["show_all", "hide_paid"] else 0
        )

        st.markdown("**Rayon**")
        radius_km = st.slider("Rayon (km)", 1, 20, int(st.session_state.last_radius_km))

        top_n = st.slider("Number of results", 5, 20, int(st.session_state.last_top_n))

        run = st.form_submit_button("Search")

    st.divider()

    # ✅ Plan a game at bottom, editable anytime (no need to Search first)
    st.subheader("Plan a game")
    st.session_state.plan_mode = st.checkbox("Plan a game (optional)", value=st.session_state.plan_mode)

    if st.session_state.plan_mode:
        st.session_state.plan_date = st.date_input("Date", value=st.session_state.plan_date)
        st.session_state.plan_time = st.time_input("Time", value=st.session_state.plan_time)
        st.session_state.plan_players = int(
            st.number_input("Players", min_value=2, max_value=30, value=int(st.session_state.plan_players), step=1)
        )
    st.caption("Plan OFF → message sans date/heure/joueurs + pas de calendrier.")

# ============================
# 10) Run pipeline
# ============================
if run:
    st.session_state.last_error = None
    st.session_state.df_top = None
    st.session_state.folium_map = None
    st.session_state.selected_pitch_id = None
    st.session_state.selected_lat = None
    st.session_state.selected_lon = None

    # Persist latest search
    st.session_state.last_address = address
    st.session_state.last_profile_name = profile_name
    st.session_state.last_pitch_type = pitch_type
    st.session_state.last_paid_filter = paid_filter
    st.session_state.last_radius_km = radius_km
    st.session_state.last_top_n = top_n

    try:
        coords = geocode_address(address.strip())
        if coords is None:
            st.session_state.last_error = "Address not found. Try a more precise address."
        else:
            user_lat, user_lon = coords
            st.session_state.origin_lat = user_lat
            st.session_state.origin_lon = user_lon

            osm = overpass_get_pitches(user_lat, user_lon, radius_m=int(radius_km * 1000))
            df = pitches_to_df(osm, user_lat, user_lon)

            if df.empty:
                st.session_state.last_error = "No pitches found. Try increasing the radius or changing the address."
            else:
                # Filter within chosen radius
                df = df[df["distance_km"] <= float(radius_km)].copy()
                if df.empty:
                    st.session_state.last_error = "No pitches within the selected radius."
                else:
                    df = apply_paid_filter(df, paid_filter=paid_filter)
                    if df.empty:
                        st.session_state.last_error = "No pitches after paid filter."
                    else:
                        mode = PROFILES[profile_name]["mode"]
                        df = add_eta_minutes(df, mode)
                        df = add_recommendation_score(df, profile_name, pitch_type)

                        df_filtered = filter_by_pitch_type(df, pitch_type)
                        if df_filtered.empty:
                            df_filtered = df

                        df_ranked = df_filtered.sort_values(
                            ["score_raw", "distance_km"],
                            ascending=[False, True]
                        ).reset_index(drop=True)

                        df_top = df_ranked.head(int(top_n)).copy()
                        st.session_state.df_top = df_top

                        if not df_top.empty:
                            st.session_state.selected_pitch_id = df_top.iloc[0]["pitch_id"]
                            st.session_state.selected_lat = float(df_top.iloc[0]["lat"])
                            st.session_state.selected_lon = float(df_top.iloc[0]["lon"])

    except Exception as e:
        st.session_state.last_error = f"Error: {e}"

# ============================
# 11) Display results
# ============================
if st.session_state.last_error:
    st.error(st.session_state.last_error)

df_top = st.session_state.df_top
if df_top is None:
    st.info("Use the sidebar and click **Search** to display results.")
    st.stop()

if df_top.empty:
    st.warning("No results to display.")
    st.stop()

left, right = st.columns([1.25, 1])

with left:
    st.subheader("Top results")

    for _, row in df_top.iterrows():
        pitch_id = row["pitch_id"]
        name = row["name"]
        provider = row.get("provider", "Public/Other")
        surface = row.get("surface", "") or "n/a"
        eta = int(row.get("eta_min", 0))
        dist = float(row.get("distance_km", 0))
        stars5 = int(row.get("stars5", 0))
        stars_line = stars_txt(stars5)

        directions = gmaps_directions_link(
            st.session_state.origin_lat, st.session_state.origin_lon, row["lat"], row["lon"]
        )

        is_sel = (pitch_id == st.session_state.selected_pitch_id)

        # ✅ Every card has outline; selected changes color
        border = "2px solid #ff8c00" if is_sel else "1.5px solid rgba(0,0,0,0.18)"
        bg = "rgba(255,140,0,0.06)" if is_sel else "rgba(255,255,255,0.02)"
        shadow = "0 6px 18px rgba(0,0,0,0.10)" if is_sel else "0 2px 8px rgba(0,0,0,0.06)"
        accent = "#ff8c00" if is_sel else "rgba(0,0,0,0)"

        st.markdown(
            f"""
            <div style="
              border: {border};
              border-radius: 16px;
              padding: 14px;
              margin-bottom: 10px;
              background: {bg};
              box-shadow: {shadow};
              position: relative;
              overflow: hidden;
            ">
              <div style="
                position:absolute; left:0; top:0; bottom:0;
                width: 6px; background: {accent};
              "></div>

              <div style="font-size: 18px; font-weight: 750;">{name}</div>
              <div style="opacity:0.85; margin-top:6px;">
                {stars_line} &nbsp;•&nbsp; {dist} km &nbsp;•&nbsp; ~{eta} min
              </div>
              <div style="opacity:0.75; margin-top:6px; font-size: 0.92rem;">
                {provider} &nbsp;•&nbsp; Surface: {surface}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Actions: Highlight | Plan&Copy/Book | Y aller
        c1, c2, c3 = st.columns([1, 1, 1])

        with c1:
            if st.button("📍 Highlight", key=f"hl_{pitch_id}", use_container_width=True):
                st.session_state.selected_pitch_id = pitch_id
                st.session_state.selected_lat = float(row["lat"])
                st.session_state.selected_lon = float(row["lon"])
                st.rerun()

        with c2:
            if is_bookable_provider(provider):
                # No key= here (compat)
                st.link_button("Book", provider_booking_link(provider), use_container_width=True)
            else:
                with st.popover("Plan & copy"):
                    share_msg = format_share_message(
                        user_name=st.session_state.user_name,
                        user_style=st.session_state.user_style,
                        plan_mode=st.session_state.plan_mode,
                        name=name,
                        stars5=stars5,
                        profile_name=st.session_state.last_profile_name,
                        dist_km=dist,
                        eta_min=eta,
                        directions_url=directions,
                        date_=st.session_state.plan_date.strftime("%Y-%m-%d"),
                        time_=st.session_state.plan_time.strftime("%H:%M"),
                        players=st.session_state.plan_players
                    )

                    copy_button(share_msg, key=f"copy_{pitch_id}", label="Copier le message")
                    st.code(share_msg)

                    # Calendars only if plan_mode ON
                    if st.session_state.plan_mode:
                        start_local = datetime.combine(
                            st.session_state.plan_date,
                            st.session_state.plan_time
                        ).astimezone()
                        end_local = start_local + timedelta(hours=1)

                        gcal = google_calendar_link(
                            title=f"Football — {name}",
                            start_dt=start_local,
                            end_dt=end_local,
                            details=share_msg,
                            location=name
                        )
                        # No key= (compat)
                        st.link_button("Add to Google Calendar", gcal, use_container_width=True)

                        ics = build_ics_event(
                            title=f"Football — {name}",
                            start_dt=start_local,
                            end_dt=end_local,
                            description=share_msg,
                            location=name
                        )
                        st.download_button(
                            "Add to Apple Calendar (.ics)",
                            data=ics.encode("utf-8"),
                            file_name=f"pitchfinder_{pitch_id}.ics",
                            mime="text/calendar",
                            use_container_width=True,
                            key=f"ics_{pitch_id}"  # ✅ unique
                        )
                    else:
                        st.caption("Active 'Plan a game' (en bas) pour générer un événement calendrier.")

        with c3:
            # ✅ Y aller button (Apple Maps if possible else Google)
            components.html(
                go_button_html(row["lat"], row["lon"], name, element_id=f"go_{pitch_id}".replace(",", "_")),
                height=55
            )

with right:
    st.subheader("Map")

    radius_km_effective = float(st.session_state.last_radius_km)

    st.session_state.folium_map = make_map(
        st.session_state.origin_lat,
        st.session_state.origin_lon,
        df_top,
        radius_km=radius_km_effective,
        selected_id=st.session_state.selected_pitch_id,
        selected_lat=st.session_state.selected_lat,
        selected_lon=st.session_state.selected_lon
    )

    html_map = st.session_state.folium_map.get_root().render()

    # ✅ Force rerender safely without using key=
    bust = f"{st.session_state.selected_pitch_id}|{st.session_state.selected_lat}|{st.session_state.selected_lon}"
    components.html(
        html_map + f"\n<!-- bust:{bust} -->\n",
        height=650,
        width=None,
        scrolling=False
    )
