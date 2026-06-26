import requests
from datetime import datetime, timezone

LAT, LON, CITY = 52.52, 13.41, "Berlin"

resp = requests.get(
    "https://api.open-meteo.com/v1/forecast",
    params={"latitude": LAT, "longitude": LON, "current_weather": "true"},
    timeout=10,
)
resp.raise_for_status()
data = resp.json()["current_weather"]

html = f"""<!DOCTYPE html>
<html><head><title>Weather Report - {CITY}</title></head>
<body>
<h1>Weather Report: {CITY}</h1>
<p>Temperature: {data['temperature']} &deg;C</p>
<p>Wind speed: {data['windspeed']} km/h</p>
<p>Weather code: {data['weathercode']}</p>
<p>Generated: {datetime.now(timezone.utc).isoformat()}</p>
</body></html>"""

with open("/output/weather_report.html", "w") as f:
    f.write(html)

print("Report written to /output/weather_report.html")