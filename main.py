import os
import ast
import requests

from flask import Flask, jsonify, request, send_from_directory


app = Flask(__name__)


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

api_key = os.getenv("ORS_API_KEY")

# Center autocomplete/geocoding around the Rockaways.
FOCUS_LAT = 40.59408
FOCUS_LON = -73.78921

# Number of real FloodNet sensors to use in the demo.
DEMO_SENSOR_COUNT = 8

EVENTS_URL = (
    "https://data.cityofnewyork.us/resource/aq7i-eu5q.json"
)

METADATA_URL = (
    "https://data.cityofnewyork.us/resource/kb2e-tjy3.json"
)


# ---------------------------------------------------------
# FLOOD SEVERITY
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# HAZARD POLYGONS
# ---------------------------------------------------------

def make_hazard_polygon(latitude, longitude):

    # Small demonstration routing buffer around a sensor.
    # This is NOT claiming FloodNet measured this exact area.

    lat_size = 0.00033
    lon_size = 0.00039

    return [
        [
            longitude - lon_size,
            latitude - lat_size
        ],
        [
            longitude + lon_size,
            latitude - lat_size
        ],
        [
            longitude + lon_size,
            latitude + lat_size
        ],
        [
            longitude - lon_size,
            latitude + lat_size
        ],
        [
            longitude - lon_size,
            latitude - lat_size
        ]
    ]


def find_replay_start(depths):

    # Begin each historical replay when flooding first reaches
    # the demo threshold so hazards are visible immediately.

    for index, depth in enumerate(depths):

        if depth >= 0.4:
            return index

    return 0


# ---------------------------------------------------------
# LOAD REAL FLOODNET HISTORICAL EVENTS
# ---------------------------------------------------------

def load_demo_sensors():

    sensors = []

    try:

        # Pull recent historical flood events in the Rockaways.
        # We then select unique FloodNet sensors from those events.

        response = requests.get(
            EVENTS_URL,
            params={
                "$where":
                    "sensor_name like 'Q - Beach%'",
                "$order":
                    "flood_start_time DESC",
                "$limit":
                    200
            },
            timeout=15
        )

        response.raise_for_status()

        events = response.json()

    except Exception as error:

        print(
            "FloodNet event loading error:",
            error
        )

        return []


    used_sensor_ids = set()


    for event in events:

        if len(sensors) >= DEMO_SENSOR_COUNT:
            break


        sensor_id = event.get(
            "sensor_id"
        )


        if (
            not sensor_id
            or sensor_id in used_sensor_ids
        ):
            continue


        profile = event.get(
            "flood_profile_depth_inches"
        )


        if not profile:
            continue


        try:

            if isinstance(
                profile,
                str
            ):

                depths = ast.literal_eval(
                    profile
                )

            else:

                depths = profile


            depths = [
                float(depth)
                for depth in depths
            ]


            if len(depths) == 0:
                continue


            # Only use actual flood events that reached
            # the demo flood threshold.

            if max(depths) < 0.4:
                continue


        except Exception as error:

            print(
                "Flood profile parsing error:",
                sensor_id,
                error
            )

            continue


        try:

            metadata_response = requests.get(
                METADATA_URL,
                params={
                    "$where":
                        f"sensor_id='{sensor_id}'",
                    "$limit":
                        1
                },
                timeout=10
            )

            metadata_response.raise_for_status()

            metadata = metadata_response.json()


            if len(metadata) == 0:
                continue


            sensor_metadata = metadata[0]


            latitude = float(
                sensor_metadata["latitude"]
            )

            longitude = float(
                sensor_metadata["longitude"]
            )


        except Exception as error:

            print(
                "FloodNet metadata error:",
                sensor_id,
                error
            )

            continue


        replay_start = find_replay_start(
            depths
        )


        sensors.append({

            "sensor_id":
                sensor_id,

            "sensor_name":
                sensor_metadata.get(
                    "sensor_name",
                    event.get(
                        "sensor_name",
                        sensor_id
                    )
                ),

            "latitude":
                latitude,

            "longitude":
                longitude,

            "depths":
                depths,

            "index":
                replay_start,

            "replay_start":
                replay_start,

            "polygon":
                make_hazard_polygon(
                    latitude,
                    longitude
                ),

            "event_start":
                event.get(
                    "flood_start_time"
                )

        })


        used_sensor_ids.add(
            sensor_id
        )


    print(
        "Loaded",
        len(sensors),
        "FloodNet demo sensors"
    )


    return sensors


demo_sensors = load_demo_sensors()


# ---------------------------------------------------------
# GEOMETRY HELPERS
# ---------------------------------------------------------

def point_inside_polygon(
    point,
    polygon
):

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


    # All demo hazard polygons are rectangles,
    # so a bounding-box test is sufficient.

    return (
        min(longitudes)
        <= longitude
        <= max(longitudes)

        and

        min(latitudes)
        <= latitude
        <= max(latitudes)
    )


def orientation(
    a,
    b,
    c
):

    value = (
        (b[1] - a[1])
        * (c[0] - b[0])

        -

        (b[0] - a[0])
        * (c[1] - b[1])
    )


    if abs(value) < 0.000000001:
        return 0


    if value > 0:
        return 1


    return 2


def on_segment(
    a,
    b,
    c
):

    return (
        min(a[0], c[0])
        <= b[0]
        <= max(a[0], c[0])

        and

        min(a[1], c[1])
        <= b[1]
        <= max(a[1], c[1])
    )


def segments_intersect(
    p1,
    q1,
    p2,
    q2
):

    o1 = orientation(
        p1,
        q1,
        p2
    )

    o2 = orientation(
        p1,
        q1,
        q2
    )

    o3 = orientation(
        p2,
        q2,
        p1
    )

    o4 = orientation(
        p2,
        q2,
        q1
    )


    if (
        o1 != o2
        and
        o3 != o4
    ):
        return True


    if (
        o1 == 0
        and
        on_segment(
            p1,
            p2,
            q1
        )
    ):
        return True


    if (
        o2 == 0
        and
        on_segment(
            p1,
            q2,
            q1
        )
    ):
        return True


    if (
        o3 == 0
        and
        on_segment(
            p2,
            p1,
            q2
        )
    ):
        return True


    if (
        o4 == 0
        and
        on_segment(
            p2,
            q1,
            q2
        )
    ):
        return True


    return False


# ---------------------------------------------------------
# ACTIVE FLOOD POLYGONS
# ---------------------------------------------------------

def get_active_polygons():

    polygons = []


    for sensor in demo_sensors:

        if len(sensor["depths"]) == 0:
            continue


        depth = sensor["depths"][
            sensor["index"]
        ]


        if depth >= 0.4:

            polygons.append(
                sensor["polygon"]
            )


    return polygons


# ---------------------------------------------------------
# CHECK WHETHER ROUTE CROSSES ANY FLOOD AREA
# ---------------------------------------------------------

def route_intersects_flood(
    route,
    polygons
):

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


        # Check route points inside polygon.

        for point in coordinates:

            if point_inside_polygon(
                point,
                polygon
            ):

                return True


        # Check route line segments crossing polygon edges.

        for i in range(
            len(coordinates) - 1
        ):

            route_start = (
                coordinates[i]
            )

            route_end = (
                coordinates[i + 1]
            )


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


# ---------------------------------------------------------
# GEOCODING
# ---------------------------------------------------------

def geocode_address(address):

    if not api_key:

        print(
            "ORS_API_KEY is missing."
        )

        return None


    url = (
        "https://api.heigit.org/"
        "pelias/v1/search"
    )


    headers = {
        "Authorization":
            api_key
    }


    params = {

        "text":
            address,

        "size":
            1,

        "boundary.country":
            "US",

        "focus.point.lat":
            FOCUS_LAT,

        "focus.point.lon":
            FOCUS_LON

    }


    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

    except Exception as error:

        print(
            "Geocoding request error:",
            error
        )

        return None


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


    label = (
        feature["properties"].get(
            "label",
            address
        )
    )


    label = label.replace(
        ", United States",
        ""
    )


    label = label.replace(
        ", USA",
        ""
    )


    return {

        "coordinates":
            feature["geometry"]
            ["coordinates"],

        "label":
            label

    }


# ---------------------------------------------------------
# OPENROUTESERVICE ROUTING
# ---------------------------------------------------------

def get_route(
    start,
    destination,
    mode,
    avoid_polygons=None
):

    if not api_key:

        print(
            "ORS_API_KEY is missing."
        )

        return None


    if mode == "driving":

        profile = (
            "driving-car"
        )


    elif mode == "walking":

        profile = (
            "foot-walking"
        )


    else:

        return None


    url = (
        "https://api.heigit.org/"
        f"openrouteservice/v2/directions/"
        f"{profile}/geojson"
    )


    headers = {

        "Authorization":
            api_key,

        "Content-Type":
            "application/json"

    }


    body = {

        "coordinates": [
            start,
            destination
        ],

        "preference":
            "recommended"

    }


    if avoid_polygons:


        if len(avoid_polygons) == 1:

            geometry = {

                "type":
                    "Polygon",

                "coordinates": [
                    avoid_polygons[0]
                ]

            }


        else:

            geometry = {

                "type":
                    "MultiPolygon",

                "coordinates": [
                    [polygon]
                    for polygon
                    in avoid_polygons
                ]

            }


        body["options"] = {

            "avoid_polygons":
                geometry

        }


    try:

        response = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=20
        )

    except Exception as error:

        print(
            "Routing request error:",
            error
        )

        return None


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


# ---------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------

@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# ---------------------------------------------------------
# AUTOCOMPLETE
# ---------------------------------------------------------

@app.route("/autocomplete")
def autocomplete():

    text = request.args.get(
        "text",
        ""
    )


    if len(
        text.strip()
    ) < 2:

        return jsonify([])


    if not api_key:

        return jsonify([])


    url = (
        "https://api.heigit.org/"
        "pelias/v1/autocomplete"
    )


    headers = {

        "Authorization":
            api_key

    }


    params = {

        "text":
            text,

        "size":
            5,

        "boundary.country":
            "US",

        "focus.point.lat":
            FOCUS_LAT,

        "focus.point.lon":
            FOCUS_LON

    }


    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

    except Exception as error:

        print(
            "Autocomplete request error:",
            error
        )

        return jsonify([])


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
            feature[
                "geometry"
            ][
                "coordinates"
            ]
        )


        properties = feature.get(
            "properties",
            {}
        )


        country_code = (
            properties.get(
                "country_a",
                ""
            )
        )


        if (
            country_code
            and
            country_code != "USA"
        ):

            continue


        label = properties.get(
            "label",
            "Unknown location"
        )


        label = label.replace(
            ", United States",
            ""
        )


        label = label.replace(
            ", USA",
            ""
        )


        results.append({

            "label":
                label,

            "longitude":
                coordinates[0],

            "latitude":
                coordinates[1]

        })


    return jsonify(
        results
    )


# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

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


    # -----------------------------------------------------
    # START LOCATION
    # -----------------------------------------------------

    if (
        start_lat
        and
        start_lon
    ):

        start = [
            float(start_lon),
            float(start_lat)
        ]


        start_label = (
            start_text
            or
            "Current location"
        )


    else:

        start_result = (
            geocode_address(
                start_text
            )
        )


        if start_result is None:

            return jsonify({

                "error":
                    "Starting location could not be found."

            }), 400


        start = (
            start_result[
                "coordinates"
            ]
        )


        start_label = (
            start_result[
                "label"
            ]
        )


    # -----------------------------------------------------
    # DESTINATION
    # -----------------------------------------------------

    if (
        destination_lat
        and
        destination_lon
    ):

        destination = [
            float(
                destination_lon
            ),
            float(
                destination_lat
            )
        ]


        destination_label = (
            destination_text
            or
            "Destination"
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


    # -----------------------------------------------------
    # NORMAL ROUTE
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # CURRENT ACTIVE FLOOD AREAS
    # -----------------------------------------------------

    active_polygons = (
        get_active_polygons()
    )


    intersects_flood = (
        route_intersects_flood(
            normal_route,
            active_polygons
        )
    )


    # -----------------------------------------------------
    # SAFE ROUTE
    # -----------------------------------------------------

    if active_polygons:

        safe_route = get_route(
            start,
            destination,
            mode,
            active_polygons
        )


    else:

        safe_route = (
            normal_route
        )


    # If ORS cannot find a flood avoidance route,
    # keep the normal route available.

    if safe_route is None:

        safe_route = (
            normal_route
        )


    return jsonify({

        "normal":
            normal_route,

        "safe":
            safe_route,

        "intersects_flood":
            intersects_flood,

        "active_hazard_count":
            len(
                active_polygons
            ),

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


# ---------------------------------------------------------
# MULTIPLE FLOOD HAZARDS
# ---------------------------------------------------------

@app.route("/hazards")
def hazards():

    hazards_list = []


    for sensor in demo_sensors:

        if len(
            sensor["depths"]
        ) == 0:

            continue


        depth = (
            sensor[
                "depths"
            ][
                sensor[
                    "index"
                ]
            ]
        )


        hazards_list.append({

            "sensor_id":
                sensor[
                    "sensor_id"
                ],

            "sensor_name":
                sensor[
                    "sensor_name"
                ],

            "latitude":
                sensor[
                    "latitude"
                ],

            "longitude":
                sensor[
                    "longitude"
                ],

            "depth_inches":
                depth,

            "severity":
                get_severity(
                    depth
                ),

            "flood_active":
                depth >= 0.4,

            "polygon":
                sensor[
                    "polygon"
                ],

            "event_start":
                sensor.get(
                    "event_start"
                )

        })


        if (
            sensor["index"]
            <
            len(
                sensor["depths"]
            ) - 1
        ):

            sensor["index"] += 1


    return jsonify(
        hazards_list
    )


# ---------------------------------------------------------
# RESET HISTORICAL REPLAY
# ---------------------------------------------------------

@app.route("/reset")
def reset():

    for sensor in demo_sensors:

        sensor["index"] = (
            sensor[
                "replay_start"
            ]
        )


    return jsonify({

        "message":
            "Flood simulations reset",

        "sensor_count":
            len(
                demo_sensors
            )

    })


# ---------------------------------------------------------
# DEBUG / HEALTH CHECK
# ---------------------------------------------------------

@app.route("/health")
def health():

    return jsonify({

        "status":
            "ok",

        "sensor_count":
            len(
                demo_sensors
            ),

        "ors_key_loaded":
            bool(
                api_key
            )

    })


# ---------------------------------------------------------
# START SERVER
# ---------------------------------------------------------

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )


    app.run(
        host="0.0.0.0",
        port=port
    )