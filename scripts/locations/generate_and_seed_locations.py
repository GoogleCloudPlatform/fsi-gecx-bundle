# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import json
import random
from pathlib import Path
from google.cloud import bigquery
import google.auth

# 80 cities in the United States with coordinate centroids
CITIES = [
    {"city": "New York", "lat": 40.7128, "lng": -74.0060, "state": "NY", "zip": "10001"},
    {"city": "Los Angeles", "lat": 34.0522, "lng": -118.2437, "state": "CA", "zip": "90001"},
    {"city": "Chicago", "lat": 41.8781, "lng": -87.6298, "state": "IL", "zip": "60601"},
    {"city": "Houston", "lat": 29.7604, "lng": -95.3698, "state": "TX", "zip": "77001"},
    {"city": "Phoenix", "lat": 33.4484, "lng": -112.0740, "state": "AZ", "zip": "85001"},
    {"city": "Philadelphia", "lat": 39.9526, "lng": -75.1652, "state": "PA", "zip": "19101"},
    {"city": "San Antonio", "lat": 29.4241, "lng": -98.4936, "state": "TX", "zip": "78201"},
    {"city": "San Diego", "lat": 32.7157, "lng": -117.1611, "state": "CA", "zip": "92101"},
    {"city": "Dallas", "lat": 32.7767, "lng": -96.7970, "state": "TX", "zip": "75201"},
    {"city": "San Jose", "lat": 37.3382, "lng": -121.8863, "state": "CA", "zip": "95101"},
    {"city": "Austin", "lat": 30.2672, "lng": -97.7431, "state": "TX", "zip": "78701"},
    {"city": "Jacksonville", "lat": 30.3322, "lng": -81.6557, "state": "FL", "zip": "32201"},
    {"city": "Fort Worth", "lat": 32.7555, "lng": -97.3308, "state": "TX", "zip": "76101"},
    {"city": "Columbus", "lat": 39.9612, "lng": -82.9988, "state": "OH", "zip": "43201"},
    {"city": "Charlotte", "lat": 35.2271, "lng": -80.8431, "state": "NC", "zip": "28201"},
    {"city": "San Francisco", "lat": 37.7749, "lng": -122.4194, "state": "CA", "zip": "94101"},
    {"city": "Indianapolis", "lat": 39.7684, "lng": -86.1581, "state": "IN", "zip": "46201"},
    {"city": "Seattle", "lat": 47.6062, "lng": -122.3321, "state": "WA", "zip": "98101"},
    {"city": "Denver", "lat": 39.7392, "lng": -104.9903, "state": "CO", "zip": "80201"},
    {"city": "Washington", "lat": 38.9072, "lng": -77.0369, "state": "DC", "zip": "20001"},
    {"city": "Boston", "lat": 42.3601, "lng": -71.0589, "state": "MA", "zip": "02101"},
    {"city": "El Paso", "lat": 31.7619, "lng": -106.4850, "state": "TX", "zip": "79901"},
    {"city": "Nashville", "lat": 36.1627, "lng": -86.7816, "state": "TN", "zip": "37201"},
    {"city": "Detroit", "lat": 42.3314, "lng": -83.0458, "state": "MI", "zip": "48201"},
    {"city": "Oklahoma City", "lat": 35.4676, "lng": -97.5164, "state": "OK", "zip": "73101"},
    {"city": "Portland", "lat": 45.5152, "lng": -122.6784, "state": "OR", "zip": "97201"},
    {"city": "Las Vegas", "lat": 36.1716, "lng": -115.1398, "state": "NV", "zip": "89101"},
    {"city": "Memphis", "lat": 35.1495, "lng": -90.0490, "state": "TN", "zip": "38101"},
    {"city": "Louisville", "lat": 38.2527, "lng": -85.7585, "state": "KY", "zip": "40201"},
    {"city": "Baltimore", "lat": 39.2904, "lng": -76.6122, "state": "MD", "zip": "21201"},
    {"city": "Milwaukee", "lat": 43.0389, "lng": -87.9065, "state": "WI", "zip": "53201"},
    {"city": "Albuquerque", "lat": 35.0844, "lng": -106.6511, "state": "NM", "zip": "87101"},
    {"city": "Tucson", "lat": 32.2226, "lng": -110.9747, "state": "AZ", "zip": "85701"},
    {"city": "Fresno", "lat": 36.7378, "lng": -119.7871, "state": "CA", "zip": "93701"},
    {"city": "Sacramento", "lat": 38.5816, "lng": -121.4944, "state": "CA", "zip": "95801"},
    {"city": "Kansas City", "lat": 39.0997, "lng": -94.5786, "state": "MO", "zip": "64101"},
    {"city": "Mesa", "lat": 33.4152, "lng": -111.8315, "state": "AZ", "zip": "85201"},
    {"city": "Atlanta", "lat": 33.7490, "lng": -84.3880, "state": "GA", "zip": "30301"},
    {"city": "Omaha", "lat": 41.2565, "lng": -95.9345, "state": "NE", "zip": "68101"},
    {"city": "Colorado Springs", "lat": 38.8339, "lng": -104.8214, "state": "CO", "zip": "80901"},
    {"city": "Raleigh", "lat": 35.7796, "lng": -78.6382, "state": "NC", "zip": "27601"},
    {"city": "Virginia Beach", "lat": 36.8529, "lng": -75.9780, "state": "VA", "zip": "23450"},
    {"city": "Miami", "lat": 25.7617, "lng": -80.1918, "state": "FL", "zip": "33101"},
    {"city": "Oakland", "lat": 37.8044, "lng": -122.2712, "state": "CA", "zip": "94601"},
    {"city": "Minneapolis", "lat": 44.9778, "lng": -93.2650, "state": "MN", "zip": "55401"},
    {"city": "Tulsa", "lat": 36.1540, "lng": -95.9928, "state": "OK", "zip": "74101"},
    {"city": "Bakersfield", "lat": 35.3733, "lng": -119.0187, "state": "CA", "zip": "93301"},
    {"city": "Wichita", "lat": 37.6872, "lng": -97.3301, "state": "KS", "zip": "67201"},
    {"city": "Arlington", "lat": 32.7357, "lng": -97.1081, "state": "TX", "zip": "76001"},
    {"city": "Aurora", "lat": 39.7294, "lng": -104.8319, "state": "CO", "zip": "80010"},
    {"city": "Tampa", "lat": 27.9506, "lng": -82.4572, "state": "FL", "zip": "33601"},
    {"city": "New Orleans", "lat": 29.9511, "lng": -90.0715, "state": "LA", "zip": "70112"},
    {"city": "Cleveland", "lat": 41.4993, "lng": -81.6944, "state": "OH", "zip": "44101"},
    {"city": "Honolulu", "lat": 21.3069, "lng": -157.8583, "state": "HI", "zip": "96801"},
    {"city": "Anaheim", "lat": 33.8366, "lng": -117.9143, "state": "CA", "zip": "92801"},
    {"city": "Henderson", "lat": 36.0395, "lng": -114.9817, "state": "NV", "zip": "89002"},
    {"city": "Santa Ana", "lat": 33.7456, "lng": -117.8677, "state": "CA", "zip": "92701"},
    {"city": "St. Louis", "lat": 38.6270, "lng": -90.1994, "state": "MO", "zip": "63101"},
    {"city": "Riverside", "lat": 33.9806, "lng": -117.3755, "state": "CA", "zip": "92501"},
    {"city": "Corpus Christi", "lat": 27.8006, "lng": -97.3964, "state": "TX", "zip": "78401"},
    {"city": "Pittsburgh", "lat": 40.4406, "lng": -79.9959, "state": "PA", "zip": "15201"},
    {"city": "Lexington", "lat": 38.0406, "lng": -84.5007, "state": "KY", "zip": "40502"},
    {"city": "Anchorage", "lat": 61.2181, "lng": -149.9003, "state": "AK", "zip": "99501"},
    {"city": "Stockton", "lat": 37.9577, "lng": -121.2908, "state": "CA", "zip": "95201"},
    {"city": "Cincinnati", "lat": 39.1031, "lng": -84.5120, "state": "OH", "zip": "45201"},
    {"city": "St. Paul", "lat": 44.9537, "lng": -93.0900, "state": "MN", "zip": "55101"},
    {"city": "Greensboro", "lat": 36.0726, "lng": -79.7920, "state": "NC", "zip": "27401"},
    {"city": "Toledo", "lat": 41.6528, "lng": -83.5379, "state": "OH", "zip": "43601"},
    {"city": "Newark", "lat": 40.7357, "lng": -74.1724, "state": "NJ", "zip": "07101"},
    {"city": "Plano", "lat": 33.0198, "lng": -96.6989, "state": "TX", "zip": "75023"},
    {"city": "Lincoln", "lat": 40.8258, "lng": -96.6852, "state": "NE", "zip": "68501"},
    {"city": "Orlando", "lat": 28.5384, "lng": -81.3789, "state": "FL", "zip": "32801"},
    {"city": "Irvine", "lat": 33.6846, "lng": -117.8265, "state": "CA", "zip": "92602"},
    {"city": "Fort Wayne", "lat": 41.0793, "lng": -85.1394, "state": "IN", "zip": "46801"},
    {"city": "Jersey City", "lat": 40.7178, "lng": -74.0431, "state": "NJ", "zip": "07302"},
    {"city": "Durham", "lat": 35.9940, "lng": -78.8986, "state": "NC", "zip": "27701"},
    {"city": "St. Petersburg", "lat": 27.7676, "lng": -82.6403, "state": "FL", "zip": "33701"},
    {"city": "Laredo", "lat": 27.5306, "lng": -99.4803, "state": "TX", "zip": "78040"},
    {"city": "Buffalo", "lat": 42.8864, "lng": -78.8784, "state": "NY", "zip": "14201"},
    {"city": "Madison", "lat": 43.0731, "lng": -89.4012, "state": "WI", "zip": "53701"}
]

STREET_NAMES = ["Main St", "Broadway", "Market St", "Oak Ave", "Pine St", "Washington Blvd", "Elm St", "Maple Ave", "Park Ln", "Sunset Blvd"]

def generate_locations():
    random.seed(42)
    locations = []
    
    # Exactly 100 locations distributed across 80 cities.
    # 80 cities get 1 location, 20 cities get an additional location.
    extra_cities_indices = random.sample(range(len(CITIES)), 20)
    
    loc_counter = 1
    
    for idx, c in enumerate(CITIES):
        num_locations = 2 if idx in extra_cities_indices else 1
        
        for i in range(num_locations):
            loc_type = "BRANCH" if i == 0 and num_locations > 1 else random.choice(["BRANCH", "ATM"])
            
            offset_lat = random.uniform(-0.03, 0.03)
            offset_lng = random.uniform(-0.03, 0.03)
            loc_id = f"loc-{loc_counter:03d}"
            
            street_num = random.randint(100, 9999)
            street = random.choice(STREET_NAMES)
            
            name = f"Nova Horizon {c['city']} " + ("Branch" if loc_type == "BRANCH" else "ATM") + f" #{i+1}"
            hours = "Mon-Fri 9am-5pm, Sat 9am-1pm" if loc_type == "BRANCH" else "24/7"
            phone = f"{random.randint(200, 999)}-555-{random.randint(1000, 9999):04d}" if loc_type == "BRANCH" else None
            
            services = ["Safe Deposit Boxes", "Financial Advising", "Notary Public"] if loc_type == "BRANCH" else ["Withdrawal", "Deposit", "PIN Change"]
            
            locations.append({
                "id": loc_id,
                "type": loc_type,
                "name": name,
                "address": f"{street_num} {street}, {c['city']}, {c['state']} {c['zip']}",
                "latitude": c["lat"] + offset_lat,
                "longitude": c["lng"] + offset_lng,
                "hours": hours,
                "phone_number": phone,
                "metadata": {
                    "services": services,
                    "wheelchair_accessible": True,
                    "lobby_hours": "9:00 AM - 5:00 PM" if loc_type == "BRANCH" else None
                }
            })
            
            loc_counter += 1
            
    return locations

def main():
    # Since script is inside scripts/locations/, root is three levels up
    root_dir = Path(__file__).resolve().parent.parent.parent
    data_dir = root_dir / "deployment" / "bigquery" / "banking" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = data_dir / "retail_locations.jsonl"
    
    print(f"Generating 100 locations across 80 US cities...")
    locations = generate_locations()
    
    print(f"Writing data to {jsonl_path}...")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for loc in locations:
            f.write(json.dumps(loc) + "\n")
            
    # Load to BigQuery
    try:
        credentials, project_id = google.auth.default()
        if not project_id:
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError("Could not determine Google Cloud project ID.")
            
        print(f"Detected project ID: {project_id}")
        client = bigquery.Client(project=project_id, credentials=credentials)
        table_id = f"{project_id}.banking.retail_location"
        
        print(f"Loading data into {table_id}...")
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        
        with open(jsonl_path, "rb") as f:
            load_job = client.load_table_from_file(f, table_id, job_config=job_config)
            
        print("Waiting for job to complete...")
        load_job.result()
        
        table = client.get_table(table_id)
        print(f"Successfully loaded {table.num_rows} rows into {table_id}.")
        
    except Exception as e:
        print(f"Error seeding locations: {e}")
        print("Data file was written to disk, but BigQuery upload failed.")

if __name__ == "__main__":
    main()
