#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import urllib.request
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
import threading
from flask import Flask, send_file, abort

# --------------------------------------------------------------
# Configuration
# --------------------------------------------------------------
API_URL = "https://stats.nggmrs.net/api/nodes"
OUTPUT_KML = "nggmrs_repeaters.kml"
UPDATE_INTERVAL = 5 * 60  # 5 minutes (seconds)

app = Flask(__name__)  # Flask app for Replit


# --------------------------------------------------------------
# Helper: fetch JSON from the API
# --------------------------------------------------------------
def fetch_nodes():
    with urllib.request.urlopen(API_URL) as resp:
        data = resp.read().decode()
        return json.loads(data)


# --------------------------------------------------------------
# Helper: format a timestamp (Unix seconds) as a human‑readable string
# --------------------------------------------------------------
def fmt_time(ts):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# --------------------------------------------------------------
# Helper: decide which icon to use
# --------------------------------------------------------------
def icon_href(keyed, last_report):
    """Return a URL to a 32 px icon that ATAK can display."""
    now = datetime.now(tz=timezone.utc)
    age = now - datetime.fromtimestamp(last_report, tz=timezone.utc)

    if keyed == "1":
        # yellow – transmitting
        return "https://maps.google.com/mapfiles/kml/paddle/ylw-blank.png"
    elif age > timedelta(minutes=5):
        # red – stale data
        return "https://maps.google.com/mapfiles/kml/paddle/X.png"
    else:
        # green – normal
        return "https://maps.google.com/mapfiles/kml/paddle/grn-blank.png"


# --------------------------------------------------------------
# Build the KML document
# --------------------------------------------------------------
def build_kml(nodes):
    ET.register_namespace("", "http://www.opengis.net/kml/2.2")
    kml = ET.Element("{http://www.opengis.net/kml/2.2}kml")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = "NGGMRS Repeater Status"

    # shared style for the balloon
    style = ET.SubElement(doc, "Style", id="repeaterStyle")
    balloon = ET.SubElement(style, "BalloonStyle")
    ET.SubElement(balloon, "bgColor").text = "ffffffff"
    ET.SubElement(balloon, "textColor").text = "ff000000"
    ET.SubElement(balloon, "text").text = """
        <![CDATA[
        <b>$[name]</b><br/>
        Frequency: $[description]<br/>
        Last report: $[lastReport]<br/>
        Keyed: $[keyed]<br/>
        ]]>
    """

    for node in nodes:
        if node.get("hidden"):
            continue

        lat = node.get("latitude")
        lon = node.get("longitude")
        if lat is None or lon is None:
            continue

        placemark = ET.SubElement(doc, "Placemark")
        ET.SubElement(placemark, "name").text = node.get("name", "Unnamed")
        ET.SubElement(placemark,
                      "description").text = node.get("description", "")
        ET.SubElement(placemark, "styleUrl").text = "#repeaterStyle"

        # custom icon per status
        style_map = ET.SubElement(placemark, "Style")
        icon_style = ET.SubElement(style_map, "IconStyle")
        ET.SubElement(icon_style, "scale").text = "1.2"
        icon = ET.SubElement(icon_style, "Icon")
        ET.SubElement(icon, "href").text = icon_href(node.get("keyed", "0"),
                                                     node.get("time", 0))

        # extended data for the balloon template
        ext = ET.SubElement(placemark, "ExtendedData")
        ET.SubElement(ext, "Data",
                      name="lastReport").text = fmt_time(node.get("time", 0))
        ET.SubElement(
            ext, "Data",
            name="keyed").text = "Yes" if node.get("keyed") == "1" else "No"

        point = ET.SubElement(placemark, "Point")
        ET.SubElement(point, "coordinates").text = f"{lon},{lat},0"

    return ET.ElementTree(kml)


# --------------------------------------------------------------
# Periodic update logic
# --------------------------------------------------------------
def update_kml():
    """Fetch data, rebuild the KML file, and schedule the next run."""
    try:
        print(f"[{datetime.utcnow().isoformat()}] Fetching node data …")
        nodes = fetch_nodes()
        print(
            f"[{datetime.utcnow().isoformat()}] Got {len(nodes)} entries, building KML …"
        )
        tree = build_kml(nodes)
        tree.write(OUTPUT_KML, encoding="utf-8", xml_declaration=True)
        print(f"[{datetime.utcnow().isoformat()}] KML written to {OUTPUT_KML}")
    except Exception as e:
        print(f"[{datetime.utcnow().isoformat()}] ERROR: {e}")

    # schedule next run
    threading.Timer(UPDATE_INTERVAL, update_kml).start()


# --------------------------------------------------------------
# Flask routes
# --------------------------------------------------------------
@app.route("/")
def index():
    """Simple landing page."""
    return ("<h2>NGGMRS Repeater KML Service</h2>"
            "<p>Download the latest KML file: "
            '<a href="/kml">nggmrs_repeaters.kml</a></p>')


@app.route("/kml")
def serve_kml():
    """Serve the most‑recent KML file."""
    try:
        return send_file(OUTPUT_KML,
                         mimetype="application/vnd.google-earth.kml+xml")
    except FileNotFoundError:
        abort(404, description="KML file not yet generated.")


# --------------------------------------------------------------
# Entry point – start background updater then Flask
# --------------------------------------------------------------
if __name__ == "__main__":
    # start the first update immediately
    update_kml()
    # Replit expects the Flask app to run on host 0.0.0.0 and port from env
    import os
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
