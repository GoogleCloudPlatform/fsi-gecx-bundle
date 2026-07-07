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

import sys
import os
import psycopg2

def main():
    password = os.environ.get("DB_PASSWORD", "")
    if not password:
        print("Warning: DB_PASSWORD environment variable is empty or not set.", file=sys.stderr)
        
    print("Connecting to database using user: postgres")
    
    schemas = [
        "admin", "audit", "catalog", "identity", "merchants", 
        "operations", "cards", "kyc", "ledger", "origination", "ref_data"
    ]
    
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="banking",
            user="postgres",
            password=password
        )
        conn.autocommit = True
        with conn.cursor() as cursor:
            for schema in schemas:
                print(f"Dropping schema {schema} (CASCADE)...")
                cursor.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE;")
            
            print("Dropping alembic_version table...")
            cursor.execute("DROP TABLE IF EXISTS alembic_version CASCADE;")
            
        conn.close()
        print("Database schemas successfully dropped.")
    except Exception as e:
        print(f"Failed to drop schemas: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
