# Task: Weather Report

## Description
Write a Python script that:
1. Fetches the current weather for a given city using the Open-Meteo API
   (https://open-meteo.com — no API key required).
2. Generates a self-contained HTML report showing:
   - City name
   - Current temperature (°C)
   - Current weather condition
   - Timestamp of the report
3. Saves the HTML file to /output/weather_report.html

## Constraints
- Use only pre-installed packages (requests, jinja2).
- The script must run inside the sandbox with --network enabled.
- No data may be written outside /output.

## Default city
Berlin (lat 52.52, lon 13.41) unless the user specifies another.

## Success criteria
- /output/weather_report.html exists after the script runs.
- The HTML opens in a browser and shows a valid temperature value.
- Exit code is 0.
