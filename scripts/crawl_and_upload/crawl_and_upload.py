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
import xml.etree.ElementTree as ET
import hashlib
import json
import requests
from google.cloud import storage


def get_google_id_token(audience: str) -> str | None:
    try:
        import google.auth
        import google.auth.transport.requests
        from google.oauth2 import id_token

        auth_request = google.auth.transport.requests.Request()
        token = id_token.fetch_id_token(auth_request, audience)
        return token
    except Exception as e:
        print(f"Could not retrieve GCP ID token: {e}")
        return None


def crawl_and_upload():
    # 1. Configuration from environment variables
    sitemap_url = os.environ.get("SITEMAP_URL")
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    use_gcp_auth = os.environ.get("USE_GCP_AUTH", "").lower() == "true"
    manual_token = os.environ.get("BEARER_TOKEN")
    gcp_auth_audience = os.environ.get("GCP_AUTH_AUDIENCE")
    site_base_url = os.environ.get("SITE_BASE_URL")

    if not sitemap_url:
        print("Error: SITEMAP_URL environment variable is not set.")
        sys.exit(1)
    if not bucket_name:
        print("Error: GCS_BUCKET_NAME environment variable is not set.")
        sys.exit(1)

    # 2. Retrieve Bearer Token for OIDC authentication
    token = None
    if manual_token:
        token = manual_token
        print("Using manually provided BEARER_TOKEN.")
    elif use_gcp_auth:
        # Default audience is the target sitemap url domain or target url itself
        audience = gcp_auth_audience or sitemap_url
        print(f"Fetching Google ID token for audience: {audience}...")
        token = get_google_id_token(audience)
        if token:
            print("Successfully fetched Google ID token.")
        else:
            print("Warning: Could not fetch Google ID token dynamically.")

    # Create session and attach auth header
    session = requests.Session()
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})

    print(f"Starting crawl from sitemap: {sitemap_url}")
    print(f"Target GCS bucket: {bucket_name}")

    # 3. Fetch and parse sitemap
    try:
        sitemap_response = session.get(sitemap_url)
        sitemap_response.raise_for_status()
    except Exception as e:
        print(f"Error fetching sitemap from {sitemap_url}: {e}")
        sys.exit(1)

    try:
        root = ET.fromstring(sitemap_response.content)
        # Handle namespaces in sitemap XML
        namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [elem.text for elem in root.findall('.//ns:loc', namespaces)]
    except Exception as e:
        print(f"Error parsing sitemap XML: {e}")
        sys.exit(1)

    if not urls:
        print("No URLs found in the sitemap.")
        return

    print(f"Found {len(urls)} URLs in sitemap to crawl.")

    # 3. Initialize GCS Client
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
    except Exception as e:
        print(f"Error initializing GCS client or accessing bucket '{bucket_name}': {e}")
        sys.exit(1)

    base_url_override = os.environ.get("BASE_URL_OVERRIDE")

    # 5. Crawl session using Playwright (headless browser)
    from playwright.sync_api import sync_playwright

    print("Initializing Playwright headless browser...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context()
            if token:
                from urllib.parse import urlparse
                sitemap_host = urlparse(sitemap_url).netloc
                override_host = urlparse(base_url_override).netloc if base_url_override else None

                def handle_route(route):
                    req = route.request
                    req_host = urlparse(req.url).netloc
                    headers = {**req.headers}
                    if req_host == sitemap_host or (override_host and req_host == override_host):
                        headers["Authorization"] = f"Bearer {token}"
                    route.continue_(headers=headers)

                context.route("**/*", handle_route)

            # context.add_init_script("localStorage.setItem('theme', 'light')")
            page = context.new_page()
            page.on("console", lambda msg: print(f"PAGE LOG {msg.type}: {msg.text}"))
            page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))

            jsonl_lines = []

            # Crawl and upload pages
            for url in urls:
                fetch_url = url
                if base_url_override:
                    from urllib.parse import urlparse
                    parsed_orig = urlparse(url)
                    base_clean = base_url_override.rstrip('/')
                    fetch_url = f"{base_clean}{parsed_orig.path}"

                try:
                    print(f"Crawling page: {fetch_url} (origin: {url})")
                    # Navigate to the page and wait for network activity to be idle (so React finishes rendering)
                    page.goto(fetch_url, wait_until="networkidle")

                    # Keep only the main content inside the HTML body to exclude headers, footers and widgets
                    has_main = page.evaluate("() => !!document.getElementById('main-content')")
                    if not has_main:
                        print(f"Warning: 'main-content' element not found on page {fetch_url}!")
                    page.evaluate("() => { document.body.innerHTML = document.getElementById('main-content')?.outerHTML || ''; }")

                    html_content = page.content()
                    title = page.title()

                    # Build a clean GCS destination blob name for the rendered HTML file
                    parsed_path = url.replace("https://", "").replace("http://", "")
                    if parsed_path.endswith("/"):
                        html_blob_name = parsed_path + "index.html"
                    elif "." not in parsed_path.split("/")[-1]:
                        html_blob_name = parsed_path + ".html"
                    else:
                        html_blob_name = parsed_path

                    # Upload the rendered HTML file individually to GCS
                    print(f"Uploading rendered HTML file to GCS: {html_blob_name}")
                    html_blob = bucket.blob(html_blob_name)
                    html_blob.upload_from_string(html_content, content_type="text/html")

                    doc_id = hashlib.sha256(url.encode('utf-8')).hexdigest()
                    content_uri = f"gs://{bucket_name}/{html_blob_name}"

                    doc_url = url
                    if site_base_url:
                        from urllib.parse import urlparse
                        parsed_orig = urlparse(url)
                        base_clean = site_base_url.rstrip('/')
                        path = parsed_orig.path if parsed_orig.path.startswith('/') else f"/{parsed_orig.path}"
                        doc_url = f"{base_clean}{path}"
                        if parsed_orig.query:
                            doc_url += f"?{parsed_orig.query}"
                        if parsed_orig.fragment:
                            doc_url += f"#{parsed_orig.fragment}"

                    doc = {
                        "id": doc_id,
                        "structData": {
                            "title": title,
                            "uri": doc_url
                        },
                        "content": {
                            "mimeType": "text/html",
                            "uri": content_uri
                        }
                    }
                    jsonl_lines.append(json.dumps(doc))
                    print(f"Successfully processed and linked rendered content for {url}")

                except Exception as e:
                    print(f"Failed to crawl/upload URL '{url}': {e}")

            browser.close()

            # Upload the compiled NDJSON file to GCS
            if jsonl_lines:
                jsonl_content = "\n".join(jsonl_lines) + "\n"
                blob_name = "documents.ndjson"
                print(f"Uploading compiled NDJSON to GCS blob: {blob_name}")
                blob = bucket.blob(blob_name)
                blob.upload_from_string(jsonl_content, content_type="application/x-ndjson")
                print(f"Successfully uploaded {len(jsonl_lines)} documents in NDJSON format to gs://{bucket_name}/{blob_name}")
            else:
                print("No documents were successfully crawled. Skipping GCS upload.")

    except Exception as e:
        print(f"Playwright execution failed: {e}")

    print("Crawl and upload job finished.")

if __name__ == "__main__":
    crawl_and_upload()
