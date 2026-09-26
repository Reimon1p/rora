import requests
import ast
import time

url = "https://data.cityofnewyork.us/resource/aq7i-eu5q.json"

sensor_id = "Q-beach-59th-st-beach-channel-dr-1zbc0d"

params = {
    "$where": (
        f"sensor_id='{sensor_id}' "
        "AND flood_start_time='2026-04-20T01:35:56.000'"
    ),
    "$limit": 1
}

response = requests.get(url, params=params)

events = response.json()

if len(events) == 0:
    print("Flood event not found.")

else:
    event = events[0]

    depths = ast.literal_eval(
        event["flood_profile_depth_inches"]
    )

    print("Sensor:", event["sensor_name"])
    print("Flood date:", event["flood_start_time"])
    print("Maximum depth:", event["max_depth_inches"], "inches")
    print()

    for depth in depths:
        print("Current water depth:", depth, "inches")
        time.sleep(1)