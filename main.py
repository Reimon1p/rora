import os
import ast
import requests

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)

api_key = os.getenv("ORS_API_KEY")

FOCUS_LAT = 40.60
FOCUS_LON = -73.79

DEMO_SENSORS = [
    {
        "sensor_id": "Q-beach-59th-st-beach-channel-dr-1zbc0d",
        "event_time": "2026-04-20T01:35:56.000"
    },
    {
        "sensor_id": "Q-beach-84-st-0me680",
        "event_time": "2023-10-30T12:00:39.000"
    },
    {
        "sensor_id": "Q-beach-72nd-st-almeda-ave-1a5hw0",
        "event_time": "2023-09-29T02:19:06.000"
    }
]

EVENTS_URL = "https://data.cityofnewyork.us/resource/aq7i-eu5q.json"
METADATA_URL = "https://data.cityofnewyork.us/resource/kb2e-tjy3.json"


def make_hazard_polygon(latitude, longitude):

    lat_size = 0.00033
    lon_size = 0.00039

    return [
        [longitude - lon_size, latitude - lat_size],
        [longitude + lon_size, latitude - lat_size],
        [longitude + lon_size, latitude + lat_size],
        [longitude - lon_size, latitude + lat_size],
        [longitude - lon_size, latitude - lat_size]
    ]


def load_demo_sensors():

    sensors = []

    for config in DEMO_SENSORS:

        try:

            sensor_id = config["sensor_id"]

            metadata_response = requests.get(
                METADATA_URL,
                params={
                    "$where": f"sensor_id='{sensor_id}'",
                    "$limit": 1
                },
                timeout=10
            )

            metadata = metadata_response.json()

            event_response = requests.get(
                EVENTS_URL,
                params={
                    "$where": (
                        f"sensor_id='{sensor_id}' "
                        f"AND flood_start_time='{config['event_time']}'"
                    ),
                    "$limit": 1
                },
                timeout=10
            )

            events = event_response.json()

            if not metadata or not events:
                print("Could not load sensor:", sensor_id)
                continue

            latitude = float(metadata[0]["latitude"])
            longitude = float(metadata[0]["longitude"])

            depths = ast.literal_eval(
                events[0]["flood_profile_depth_inches"]
            )

            sensors.append({
                "sensor_id": sensor_id,
                "sensor_name": metadata[0]["sensor_name"],
                "latitude": latitude,
                "longitude": longitude,
                "depths": depths,
                "index": 0,
                "polygon": make_hazard_polygon(
                    latitude,
                    longitude
                )
            })

        except Exception as error:

            print(
                "Sensor loading error:",
                config["sensor_id"],
                error
            )

    return sensors


demo_sensors = load_demo_sensors()

def get_severity(depth):

    if depth < 0.4:
        return "none"

    elif depth < 1:
        return "low"

    elif depth < 2:
        return "moderate"

    elif depth < 3:
        return "high"

    else:
        return "severe"


def point_inside_polygon(point, polygon):

    longitude = point[0]
    latitude = point[1]

    longitudes = [
        coordinate[0]
        for coordinate in polygon
    ]

    latitudes = [
        coordinate[1]
        for coordinate in polygon

    ]

    return (
        min(longitudes) <= longitude <= max(longitudes)
        and
        min(latitudes) <= latitude <= max(latitudes)
    )


def orientation(a, b, c):

    value = (
        (b[1] - a[1]) * (c[0] - b[0])
        -
        (b[0] - a[0]) * (c[1] - b[1])
    )

    if abs(value) < 0.000000001:
        return 0

    if value > 0:
        return 1

    return 2


def on_segment(a, b, c):

    return (
        min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
        and
        min(a[1], c[1]) <= b[1] <= max(a[1], c[1])
    )


def segments_intersect(p1, q1, p2, q2):

    o1 = orientation(p1, q1, p2)
    o2 = orientation(p1, q1, q2)
    o3 = orientation(p2, q2, p1)
    o4 = orientation(p2, q2, q1)


    if o1 != o2 and o3 != o4:
        return True


    if o1 == 0 and on_segment(p1, p2, q1):
        return True

    if o2 == 0 and on_segment(p1, q2, q1):
        return True

    if o3 == 0 and on_segment(p2, p1, q2):
        return True

    if o4 == 0 and on_segment(p2, q1, q2):
        return True


    return False


def route_intersects_flood(route, polygons):

    if route is None:
        return False


    features = route.get(
        "features",
        []
    )


    if len(features) == 0:
        return False


    coordinates = (
        features[0]
        ["geometry"]
        ["coordinates"]
    )


    for polygon in polygons:

        if point_inside_polygon(point,polygon):
            return True


    for i in range(
        len(coordinates) - 1
    ):

        route_start = coordinates[i]
        route_end = coordinates[i + 1]


        for j in range(
            len(polygon) - 1
        ):

    if segments_intersect(
                       route_start,
                       route_end,
                       polygon[j],
                       polygon[j + 1]
                   ):
                       return True

       return False


def geocode_address(address):

    url = (
        "https://api.heigit.org/"
        "pelias/v1/search"
    )


    headers = {
        "Authorization": api_key
    }


    params = {

        "text": address,

        "size": 1,

       "focus.point.lat": FOCUS_LAT,
       "focus.point.lon": FOCUS_LON

    }


    response = requests.get(
        url,
        headers=headers,
        params=params
    )


    if response.status_code != 200:

        print(
            "Geocoding error:",
            response.status_code
        )

        print(
            response.text
        )

        return None


    data = response.json()

    features = data.get(
        "features",
        []
    )


    if len(features) == 0:
        return None


    feature = features[0]


    return {

        "coordinates":
            feature["geometry"]["coordinates"],

        "label":
            feature["properties"].get(
                "label",
                address
            )

    }

def get_route(
    start,
    destination,
    mode,
    avoid_polygons=None
):

    if mode == "driving":

        profile = "driving-car"

    elif mode == "walking":

        profile = "foot-walking"

    else:

        return None


    url = (
        "https://api.heigit.org/"
        f"openrouteservice/v2/directions/{profile}/geojson"
    )


    headers = {

        "Authorization": api_key,

        "Content-Type": "application/json"

    }


    body = {

        "coordinates": [
            start,
            destination
        ],

        "preference": "recommended"

    }


    if avoid_polygons:

        if len(avoid_polygons) == 1:

            geometry = {
                "type": "Polygon",
                "coordinates": [
                    avoid_polygons[0]
                ]
            }

        else:

            geometry = {
                "type": "MultiPolygon",
                "coordinates": [
                    [polygon]
                    for polygon in avoid_polygons
                ]
            }

        body["options"] = {
            "avoid_polygons": geometry
        }


    response = requests.post(
        url,
        json=body,
        headers=headers
    )


    if response.status_code != 200:

        print(
            "Routing error:",
            response.status_code
        )

        print(
            response.text
        )

        return None


    return response.json()


@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


@app.route("/autocomplete")
def autocomplete():

    text = request.args.get(
        "text",
        ""
    )


    if len(text.strip()) < 2:
        return jsonify([])


    url = (
        "https://api.heigit.org/"
        "pelias/v1/autocomplete"
    )


    headers = {
        "Authorization": api_key
    }


    params = {

        "text": text,

        "size": 5,

        "focus.point.lat":
            FOCUS_LAT,

        "focus.point.lon":
            FOCUS_LON

    }


    response = requests.get(
        url,
        headers=headers,
        params=params
    )


    if response.status_code != 200:

        print(
            "Autocomplete error:",
            response.status_code
        )

        print(
            response.text
        )

        return jsonify([])


    data = response.json()

    results = []


    for feature in data.get(
        "features",
        []
    ):

        coordinates = (
            feature["geometry"]["coordinates"]
        )

        properties = feature.get(
            "properties",
            {}
        )


        results.append({

            "label":
                properties.get(
                    "label",
                    "Unknown location"
                ),

            "longitude":
                coordinates[0],

            "latitude":
                coordinates[1]

        })


    return jsonify(
        results
    )
def get_active_polygons():

    polygons = []

    for sensor in demo_sensors:

        depth = sensor["depths"][
            sensor["index"]
        ]

        if depth >= 0.4:

            polygons.append(
                sensor["polygon"]
            )

    return polygons

@app.route("/routes")
def routes():

    mode = request.args.get(
        "mode",
        "driving"
    )


    start_text = request.args.get(
        "start",
        ""
    )

    destination_text = request.args.get(
        "destination",
        ""
    )


    start_lat = request.args.get(
        "start_lat"
    )

    start_lon = request.args.get(
        "start_lon"
    )

    destination_lat = request.args.get(
        "destination_lat"
    )

    destination_lon = request.args.get(
        "destination_lon"
    )


    if start_lat and start_lon:

        start = [
            float(start_lon),
            float(start_lat)
        ]

        start_label = (
            start_text
            or "Current location"
        )

    else:

        start_result = geocode_address(
            start_text
        )


        if start_result is None:

            return jsonify({

                "error":
                    "Starting location could not be found."

            }), 400


        start = (
            start_result["coordinates"]
        )

        start_label = (
            start_result["label"]
        )


    if (
        destination_lat
        and destination_lon
    ):

        destination = [
            float(destination_lon),
            float(destination_lat)
        ]

        destination_label = (
            destination_text
            or "Destination"
        )

    else:

        destination_result = (
            geocode_address(
                destination_text
            )
        )


        if destination_result is None:

            return jsonify({

                "error":
                    "Destination could not be found."

            }), 400


        destination = (
            destination_result[
                "coordinates"
            ]
        )

        destination_label = (
            destination_result[
                "label"
            ]
        )


    normal_route = get_route(
        start,
        destination,
        mode
    )


    if normal_route is None:

        return jsonify({

            "error":
                "The normal route could not be calculated."

        }), 500


   active_polygons = get_active_polygons()


   intersects_flood = (
       route_intersects_flood(
           normal_route,
           active_polygons
       )
   )


   safe_route = get_route(
       start,
       destination,
       mode,
       active_polygons
   )


    if safe_route is None:

        safe_route = normal_route


    return jsonify({

        "normal":
            normal_route,

        "safe":
            safe_route,

        "intersects_flood":
            intersects_flood,

        "start": {

            "label":
                start_label,

            "coordinates":
                start

        },

        "destination": {

            "label":
                destination_label,

            "coordinates":
                destination

        }

    })

@app.route("/hazards")
def hazards():

    hazards = []

    for sensor in demo_sensors:

        depth = sensor["depths"][
            sensor["index"]
        ]

        hazards.append({

            "sensor_id":
                sensor["sensor_id"],

            "sensor_name":
                sensor["sensor_name"],

            "latitude":
                sensor["latitude"],

            "longitude":
                sensor["longitude"],

            "depth_inches":
                depth,

            "severity":
                get_severity(depth),

            "flood_active":
                depth >= 0.4,

            "polygon":
                sensor["polygon"]

        })


        if (
            sensor["index"]
            < len(sensor["depths"]) - 1
        ):

            sensor["index"] += 1


    return jsonify(
        hazards
    )
    @app.route("/reset")
     def reset():

         for sensor in demo_sensors:

             sensor["index"] = 0

         return jsonify({
             "message":
                 "Flood simulations reset"
         })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )