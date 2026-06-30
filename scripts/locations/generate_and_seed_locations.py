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
import sys
import json
from pathlib import Path

def main():
    root_dir = Path(__file__).resolve().parent.parent.parent
    banking_service_dir = root_dir / "banking-service"
    jsonl_path = banking_service_dir / "resources" / "data" / "retail_locations.jsonl"
    
    if not jsonl_path.exists():
        print(f"Error: Seed file not found at {jsonl_path}")
        sys.exit(1)
        
    if str(banking_service_dir) not in sys.path:
        sys.path.insert(0, str(banking_service_dir))
        
    from utils.database import SessionLocal
    import models.identity as identity_models
    
    print(f"Reading static locations seed file from {jsonl_path}...")
    locations = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                locations.append(json.loads(line))
                
    print(f"Seeding {len(locations)} locations into SQL identity.retail_locations...")
    db = SessionLocal()
    try:
        db.query(identity_models.RetailLocation).delete()
        for loc in locations:
            db_loc = identity_models.RetailLocation(
                name=loc["name"],
                type=loc["type"],
                address=loc["address"],
                latitude=loc["latitude"],
                longitude=loc["longitude"],
                hours=loc.get("hours"),
                phone_number=loc.get("phone_number"),
            )
            db.add(db_loc)
        db.commit()
        count = db.query(identity_models.RetailLocation).count()
        print(f"Successfully seeded {count} rows into identity.retail_locations.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding to SQL database: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
