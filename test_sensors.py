import requests

url = "https://data.cityofnewyork.us/resource/kb2e-tjy3.json"

sensor_id = "Q-beach-59th-st-beach-channel-dr-1zbc0d"

params = {
    "$where": f"sensor_id='{sensor_id}'"
}

response = requests.get(url, params=params)

data = response.json()

if len(data) == 0:
    print("Sensor not found.")

else:
    sensor = data[0]

    print("Name:", sensor.get("sensor_name"))
    print("Street:", sensor.get("street_name"))
    print("Latitude:", sensor.get("latitude"))
    print("Longitude:", sensor.get("longitude"))
    print("Location:", sensor.get("location"))